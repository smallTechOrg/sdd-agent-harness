"""Database connector base class + factory.

The query/sync path must never branch on database type. Every connector **inherits from
:class:`BaseConnector`** and implements the same methods returning the same shapes, so callers use any
connector interchangeably without checking its type. ``get_connector`` dispatches on ``type`` to the
concrete subclass. New engines = one new subclass + one branch here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from mcp.server.fastmcp import FastMCP

from data_analysis_agent.tools.connectors.uri import DatasetURI
from data_analysis_agent.tools.mcp.server import DEFAULT_MAX_ROWS


class DatasetConnectionError(Exception):
    """A database's URI could not be connected/validated. Messages are ALWAYS credential-free."""


class BaseConnector(ABC):
    """How the app validates, **inspects**, and serves a database (parquet, postgres, sqlite, …).

    The connector is the single source of truth for a database's physical tables: it inspects the
    underlying store live (``discover_tables``) — the app stores no table catalog. Subclasses differ only
    in their internals; the method signatures and returned shapes are identical across all of them.
    """

    def __init__(self, server: dict) -> None:
        self._server = server
        self._uri = DatasetURI(server.get("uri") or "")

    # --- required (type-specific internals) -------------------------------

    @abstractmethod
    def connection_check(self) -> None:
        """Validate the database is reachable/readable; raise ``DatasetConnectionError`` on failure.

        Abstracts the type-specific check (parquet: the directory is accessible — zero tables is valid;
        external: a real connect). Never leaks credentials.
        """

    @abstractmethod
    def discover_tables(self) -> list[dict]:
        """Inspect the store and return its tables (**sync only** — not on the serving path).

        ``[{table_name, parquet_path?, column_names, schema, row_count}]`` — may be empty.
        """

    @abstractmethod
    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS) -> FastMCP:
        """Build the in-process MCP server (one generic ``query`` tool) over the **given** tables.

        ``table_names`` come from the caller (the resources table outside sync; freshly-discovered tables
        during sync) — ``build_server`` does NOT inspect, so the serving path never re-hits the store's
        metadata. The connector knows how to materialize a view for each named table for its type.
        """

    # --- optional (sensible defaults; override when the store supports it) -

    def discover_relationships(self) -> list[dict]:
        """Foreign-key relationships ``[{from, to, on}]`` when the store exposes them (default: none)."""
        return []

    def drop_table(self, table_name: str) -> None:
        """Remove a table from the database (default: no-op — external stores are never mutated)."""
        return None


# The database (MCP-server) types the UI offers. ``parquet`` is the internal file-upload type; the rest
# are external (a connection URI). One entry = one connector below.
# ``(value, label, is_external, uri_hint)`` — ``uri_hint`` is the per-type placeholder the UI shows in
# the Connection-URI field once that type is selected (empty for the file-upload type).
DATABASE_TYPES: list[tuple[str, str, bool, str]] = [
    ("parquet", "Upload a file", False, ""),
    ("postgresql", "PostgreSQL", True, "postgresql://user:pass@host:5432/dbname"),
    ("sqlite", "SQLite", True, "sqlite:///path/to/file.db"),
    ("mongodb", "MongoDB", True, "mongodb://host:27017/dbname"),
    ("snowflake", "Snowflake", True, "snowflake://user:pw@account/DB/SCHEMA"),
]

EXTERNAL_TYPES = frozenset(v for v, _, ext, _ in DATABASE_TYPES if ext)

# type → (module, class) registry. The connector module is imported lazily (avoids a base↔connector
# import cycle and keeps each external driver optional — drivers are imported inside the methods).
_REGISTRY: dict[str, tuple[str, str]] = {
    "parquet": ("parquet", "ParquetConnector"),
    "postgresql": ("postgres", "PostgresConnector"),
    "postgres": ("postgres", "PostgresConnector"),  # alias
    "sqlite": ("sqlite", "SQLiteConnector"),
    "mongodb": ("mongodb", "MongoDBConnector"),
    "snowflake": ("snowflake", "SnowflakeConnector"),
}


def get_connector(server: dict) -> BaseConnector:
    """Return the connector for a database dict (``type`` + ``uri`` + ``name``).

    Dispatch is a registry lookup (no type branching); the connector inspects its own tables (no catalog
    passed in).

    Raises:
        DatasetConnectionError: for an unknown database type.
    """
    import importlib
    entry = _REGISTRY.get((server.get("type") or "parquet").lower())
    if entry is None:
        raise DatasetConnectionError(f"Unsupported database type: {server.get('type')!r}")
    module, cls = entry
    connector_cls = getattr(importlib.import_module(f"data_analysis_agent.tools.connectors.{module}"), cls)
    return connector_cls(server)
