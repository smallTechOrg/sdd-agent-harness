"""Session-scoped pool of in-process MCP servers — the agent's MCP client layer.

A **session** owns one pool: one DuckDB-backed `FastMCP` server per attached data source,
built lazily on the session's first query and reused by every later query. This is the ONLY
module that imports ``mcp.shared.memory`` (the in-memory transport), so swapping to
stdio / Streamable-HTTP / the v2 ``mcp.client.Client`` stays local.

Concurrency (see spec/product/07-agent-graph.md):
- LangGraph runs each node in its own asyncio task, so MCP ``ClientSession``s are **transient**
  (opened/closed within a single call). The pool holds only plain objects across nodes/queries:
  the built ``FastMCP`` servers and their DuckDB connections.
- A session's DuckDB connection is not concurrency-safe, so queries on one session are
  serialized by a per-session ``threading.Lock`` (held by ``run_pipeline`` for the whole query).
- Pools are idle/LRU-evicted; eviction skips sessions whose lock is currently held (in use).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from importlib.metadata import version

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import DataSourceRow, SessionDataSourceRow
from data_analysis_agent.db.session import create_db_session
from data_analysis_agent.tools.mcp.server import build_server
from data_analysis_agent.tools.table_naming import sql_table_name

log = structlog.get_logger()

# Relies on the in-memory transport helper, which exists in mcp 1.x and is removed in 2.x.
_MCP_VERSION = version("mcp")
if not _MCP_VERSION.startswith("1."):
    raise RuntimeError(
        f"mcp {_MCP_VERSION} is installed but this code targets the 1.x in-memory transport. "
        f"Pin mcp==1.28.0."
    )


class NoDataSourcesError(Exception):
    """Raised when a session has no attached data sources to build a pool from."""


@dataclass
class _ToolEntry:
    server: FastMCP
    server_tool_name: str  # name on the server, e.g. "run_query"
    table_name: str
    description: str
    parameter_schema: dict


@dataclass
class SessionPool:
    """One session's MCP servers, addressed by namespaced tool key (``<table>__<tool>``)."""

    session_id: str
    entries: dict[str, _ToolEntry]
    servers: list[FastMCP]
    column_names: list[str]
    last_used: float

    def list_tools(self) -> list[dict]:
        """Agent-facing tool descriptors for the planning prompt."""
        return [
            {
                "name": key,
                "table_name": e.table_name,
                "description": e.description,
                "parameter_schema": e.parameter_schema,
            }
            for key, e in self.entries.items()
        ]

    async def call_tool(self, key: str, arguments: dict) -> tuple[str, bool]:
        """Invoke a namespaced tool via a transient session; ``(text, is_error)``."""
        entry = self.entries.get(key)
        if entry is None:
            valid = ", ".join(self.entries) or "(none)"
            return f"Unknown tool '{key}'. Valid tools: {valid}.", True
        async with create_connected_server_and_client_session(entry.server) as session:
            result = await session.call_tool(entry.server_tool_name, arguments)
        text = result.content[0].text if result.content else ""
        return text, bool(result.isError)

    def aclose(self) -> None:
        """Close every server's DuckDB connection (plain, task-safe)."""
        for server in self.servers:
            conn = getattr(server, "_duckdb_conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass


class SessionPoolManager:
    """Builds, caches, serializes, and evicts one MCP pool per session."""

    def __init__(self, max_pools: int, idle_seconds: float) -> None:
        self._pools: dict[str, SessionPool] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._registry = threading.Lock()  # guards _pools and _locks
        self._max_pools = max_pools
        self._idle_seconds = idle_seconds

    def session_lock(self, session_id: str) -> threading.Lock:
        """Return the per-session lock (created on first use); never evicted."""
        with self._registry:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = self._locks[session_id] = threading.Lock()
            return lock

    async def acquire(self, session_id: str) -> SessionPool:
        """Return the session's pool, building it lazily on first use.

        Call while holding ``session_lock(session_id)`` so a session never builds twice.
        Raises :class:`NoDataSourcesError` if the session has no sources.
        """
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is not None:
                pool.last_used = time.monotonic()
                return pool

        pool = await self._build(session_id)  # async (list_tools) — outside the registry lock

        with self._registry:
            existing = self._pools.get(session_id)
            if existing is not None:  # built concurrently elsewhere — keep the first
                pool.aclose()
                existing.last_used = time.monotonic()
                return existing
            self._pools[session_id] = pool
            self._evict_locked()
            log.info("session_pool.built", session_id=session_id, sources=len(pool.servers),
                     tools=len(pool.entries), active_pools=len(self._pools))
            return pool

    def snapshot(self, session_id: str) -> tuple[list[dict], list[str]]:
        """Return ``(tools, column_names)`` for a built pool (read by ``plan_action``)."""
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is None:
                return [], []
            pool.last_used = time.monotonic()
            return pool.list_tools(), list(pool.column_names)

    async def call_tool(self, session_id: str, key: str, arguments: dict) -> tuple[str, bool]:
        """Route a tool call to the session's pool (must be acquired first)."""
        with self._registry:
            pool = self._pools.get(session_id)
            if pool is not None:
                pool.last_used = time.monotonic()
        if pool is None:
            return f"No MCP pool for session '{session_id}'.", True
        return await pool.call_tool(key, arguments)

    def close(self, session_id: str) -> None:
        """Close and forget a session's pool (on session delete). Idempotent."""
        with self._registry:
            pool = self._pools.pop(session_id, None)
            self._locks.pop(session_id, None)
        if pool is not None:
            pool.aclose()
            log.info("session_pool.closed", session_id=session_id)

    def close_all(self) -> None:
        """Close every pool (on app shutdown)."""
        with self._registry:
            pools = list(self._pools.values())
            self._pools.clear()
            self._locks.clear()
        for pool in pools:
            pool.aclose()

    # ---- internals -------------------------------------------------------

    async def _build(self, session_id: str) -> SessionPool:
        sources = _load_sources(session_id)
        if not sources:
            raise NoDataSourcesError("No data sources attached to this session")
        max_rows = get_settings().mcp_max_result_rows
        entries: dict[str, _ToolEntry] = {}
        servers: list[FastMCP] = []
        column_names: list[str] = []
        for source in sources:
            server = build_server(source, source.get("capability_description") or "", max_rows=max_rows)
            servers.append(server)
            table = source["table_name"]
            column_names.extend(f"{table}.{c}" for c in (source.get("column_names") or []))
            async with create_connected_server_and_client_session(server) as session:
                listed = await session.list_tools()
            for tool in listed.tools:
                entries[f"{table}__{tool.name}"] = _ToolEntry(
                    server=server, server_tool_name=tool.name, table_name=table,
                    description=tool.description or "",
                    parameter_schema=_input_properties(tool.inputSchema),
                )
        return SessionPool(session_id, entries, servers, column_names, time.monotonic())

    def _evict_locked(self) -> None:
        """Evict idle + over-cap pools, skipping in-use (locked) sessions. Holds ``_registry``."""
        now = time.monotonic()
        for sid, pool in list(self._pools.items()):
            if now - pool.last_used > self._idle_seconds:
                self._try_close_locked(sid)
        while len(self._pools) > self._max_pools:
            sid = min(self._pools, key=lambda s: self._pools[s].last_used)
            if not self._try_close_locked(sid):
                break  # everything left is in use — stop to avoid spinning

    def _try_close_locked(self, sid: str) -> bool:
        """Close a pool iff its session is not currently in use. Holds ``_registry``."""
        lock = self._locks.get(sid)
        if lock is not None and not lock.acquire(blocking=False):
            return False  # in use
        try:
            pool = self._pools.pop(sid, None)
            if pool is not None:
                pool.aclose()
                log.info("session_pool.evicted", session_id=sid)
            return True
        finally:
            if lock is not None:
                lock.release()


def _input_properties(input_schema: dict | None) -> dict:
    """Reduce an MCP ``inputSchema`` to its property map for the planning prompt."""
    if not input_schema:
        return {}
    return input_schema.get("properties", input_schema)


def _load_sources(session_id: str) -> list[dict]:
    """Load a session's attached data sources as serialisable dicts (incl. table name)."""
    with create_db_session() as db:
        links = (
            db.query(SessionDataSourceRow)
            .filter(SessionDataSourceRow.session_id == session_id)
            .all()
        )
        rows = [db.get(DataSourceRow, link.data_source_id) for link in links]
        return [_serialize_source(r) for r in rows if r is not None]


def _serialize_source(ds: DataSourceRow) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "table_name": sql_table_name(ds.name),
        "parquet_path": ds.parquet_path,
        "column_names": ds.column_names,
        "row_count": ds.row_count,
        "capability_description": ds.capability_description,
    }


_manager: SessionPoolManager | None = None


def get_manager() -> SessionPoolManager:
    """Return the process-wide :class:`SessionPoolManager` singleton."""
    global _manager
    if _manager is None:
        s = get_settings()
        _manager = SessionPoolManager(s.max_session_pools, s.session_pool_idle_seconds)
    return _manager
