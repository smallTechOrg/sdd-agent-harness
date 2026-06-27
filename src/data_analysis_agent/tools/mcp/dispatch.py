"""DB-backed MCP JSON-RPC 2.0 dispatcher for ``POST /database/{id}``.

Answers the MCP read surface (tools/list+call, resources/list+read, prompts/list+get) directly from
the database's stored capability rows — it does NOT use FastMCP (which cannot represent custom
inputSchema / resources / prompts). Canned tools execute via the shared DuckDB read-only path with
parameter binding, over views built from the **resources table** (no store inspection). This is a
different surface from the agent's session pool (``tools/mcp/pool.py``).

It also serves the write surface (``MUTATION_METHODS``): ``tools|prompts|resources`` ``add``/``update``
(LLM-driven additive cascade) and ``delete`` (manual hard-delete + pruning cascade) — each in one
transaction (``_mutate``/``_delete`` roll back on any failure); the route bumps the version once and
refreshes pools post-commit.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime

import structlog
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import data_analysis_agent.tools.sync as sync
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import (
    McpPromptRow,
    McpResourceRow,
    DatabaseRow,
    McpToolRow,
)
from data_analysis_agent.tools.connectors.base import DatasetConnectionError, get_connector
from data_analysis_agent.tools.mcp.server import RecoverableQueryError, _run_select_params, bind_params

log = structlog.get_logger()

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

# Non-standard write methods (the route invalidates pools after these succeed). add/update apply an
# LLM-driven additive cascade; delete is a MANUAL hard-delete + an LLM-driven pruning cascade.
MUTATION_METHODS = frozenset({
    "tools/add", "tools/update", "tools/delete",
    "prompts/add", "prompts/update", "prompts/delete",
    "resources/add", "resources/update", "resources/delete",
})


def handle_jsonrpc(db: Session, server: DatabaseRow, payload: dict) -> dict:
    """Route a JSON-RPC request over a server's stored capabilities; return a JSON-RPC response."""
    req_id = payload.get("id") if isinstance(payload, dict) else None
    method = payload.get("method") if isinstance(payload, dict) else None
    params = payload.get("params") or {}
    try:
        handler = _METHODS.get(method)
        if handler is None:
            return _error(req_id, METHOD_NOT_FOUND, f"Unknown method: {method!r}")
        return _result(req_id, handler(db, server, params))
    except _RpcError as exc:
        return _error(req_id, exc.code, exc.message)
    except Exception as exc:  # never leak a stack trace as a 500
        log.error("mcp_dispatch.error", method=method, error=str(exc))
        return _error(req_id, INVALID_PARAMS, str(exc))


# --- methods ----------------------------------------------------------------

def _tools_list(db, server, params):
    rows, cursor = _page(db, McpToolRow, server.id, params)
    tools = []
    for r in rows:
        tool = {"name": r.name, "description": r.description, "inputSchema": r.input_schema}
        if r.title:
            tool["title"] = r.title
        if r.output_schema is not None:
            tool["outputSchema"] = r.output_schema
        if r.annotations is not None:
            tool["annotations"] = r.annotations
        tools.append(tool)
    return _with_cursor({"tools": tools}, cursor)


def _tools_call(db, server, params):
    name = params.get("name")
    arguments = params.get("arguments") or {}
    row = _active_one(db, McpToolRow, server.id, McpToolRow.name == name)
    if row is None:
        raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name!r}")
    try:
        table_names = [t["table_name"] for t in sync.active_entity_tables(db, server.id)]
        text = _execute_canned(server, row, arguments, table_names)
        return {"content": [{"type": "text", "text": text}], "isError": False}
    except (RecoverableQueryError, DatasetConnectionError, Exception) as exc:
        return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "isError": True}


def _resources_list(db, server, params):
    rows, cursor = _page(db, McpResourceRow, server.id, params)
    resources = []
    for r in rows:
        res = {"uri": r.uri, "name": r.name}
        if r.title:
            res["title"] = r.title
        if r.description:
            res["description"] = r.description
        if r.mime_type:
            res["mimeType"] = r.mime_type
        resources.append(res)
    return _with_cursor({"resources": resources}, cursor)


def _resources_read(db, server, params):
    uri = params.get("uri")
    row = _active_one(db, McpResourceRow, server.id, McpResourceRow.uri == uri)
    if row is None:
        raise _RpcError(INVALID_PARAMS, f"Unknown resource: {uri!r}")
    content = row.content  # schema resource stores its relationships/FKs in content (source of truth)
    text = json.dumps(content) if content is not None else (row.description or "")
    return {"contents": [{"uri": row.uri, "mimeType": row.mime_type or "application/json", "text": text}]}


def _prompts_list(db, server, params):
    rows, cursor = _page(db, McpPromptRow, server.id, params)
    prompts = []
    for r in rows:
        p = {"name": r.name, "arguments": r.arguments}
        if r.title:
            p["title"] = r.title
        if r.description:
            p["description"] = r.description
        prompts.append(p)
    return _with_cursor({"prompts": prompts}, cursor)


def _prompts_get(db, server, params):
    name = params.get("name")
    row = _active_one(db, McpPromptRow, server.id, McpPromptRow.name == name)
    if row is None:
        raise _RpcError(INVALID_PARAMS, f"Unknown prompt: {name!r}")
    return {"description": row.description or "", "messages": row.template or []}


# --- mutation methods (Phase B) ---------------------------------------------

def _need_name(definition):
    if not definition.get("name"):
        raise _RpcError(INVALID_PARAMS, "definition.name is required.")


def _need_uri(definition):
    if not definition.get("uri"):
        raise _RpcError(INVALID_PARAMS, "definition.uri is required.")


def _mutate(db, server, params, op_fn, need_key):
    """Apply a client-supplied capability + its additive cascade; roll back on ANY failure."""
    definition = params.get("definition")
    if not isinstance(definition, dict):
        raise _RpcError(INVALID_PARAMS, "params.definition (an object) is required.")
    need_key(definition)
    try:
        result = op_fn(db, server, definition)
    except sync.ValidationError as exc:
        db.rollback()
        raise _RpcError(INVALID_PARAMS, str(exc))
    except _RpcError:
        db.rollback()
        raise
    except Exception as exc:  # IntegrityError, etc. — never half-commit a mutation
        db.rollback()
        raise _RpcError(INVALID_PARAMS, str(exc))
    return {
        "ok": True,
        "version": server.version,
        "applied": {"child": result.child, "op": result.op, "key": result.key},
        "cascade": {"tools": result.tools_changed, "prompts": result.prompts_changed},
        "status": result.status,
    }


def _tools_add(db, server, params):       return _mutate(db, server, params, sync.add_tool, _need_name)
def _tools_update(db, server, params):    return _mutate(db, server, params, sync.update_tool, _need_name)
def _prompts_add(db, server, params):     return _mutate(db, server, params, sync.add_prompt, _need_name)
def _prompts_update(db, server, params):  return _mutate(db, server, params, sync.update_prompt, _need_name)
def _resources_add(db, server, params):   return _mutate(db, server, params, sync.add_resource, _need_uri)
def _resources_update(db, server, params): return _mutate(db, server, params, sync.update_resource, _need_uri)


def _delete(db, server, params, op_fn, key_name):
    """Manually hard-delete a capability by key, then run its pruning cascade; roll back on failure."""
    key = params.get(key_name)
    if not key:
        raise _RpcError(INVALID_PARAMS, f"params.{key_name} is required.")
    try:
        result = op_fn(db, server, key)
    except sync.ValidationError as exc:
        db.rollback()
        raise _RpcError(INVALID_PARAMS, str(exc))
    except _RpcError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise _RpcError(INVALID_PARAMS, str(exc))
    return {
        "ok": True,
        "version": server.version,
        "applied": {"child": result.child, "op": result.op, "key": result.key},
        "cascade": {"tools": result.tools_changed, "prompts": result.prompts_changed},
        "status": result.status,
    }


def _tools_delete(db, server, params):     return _delete(db, server, params, sync.delete_tool, "name")
def _prompts_delete(db, server, params):   return _delete(db, server, params, sync.delete_prompt, "name")
def _resources_delete(db, server, params): return _delete(db, server, params, sync.delete_resource, "uri")


_METHODS = {
    "tools/list": _tools_list,
    "tools/call": _tools_call,
    "resources/list": _resources_list,
    "resources/read": _resources_read,
    "prompts/list": _prompts_list,
    "prompts/get": _prompts_get,
    "tools/add": _tools_add,
    "tools/update": _tools_update,
    "tools/delete": _tools_delete,
    "prompts/add": _prompts_add,
    "prompts/update": _prompts_update,
    "prompts/delete": _prompts_delete,
    "resources/add": _resources_add,
    "resources/update": _resources_update,
    "resources/delete": _resources_delete,
}


# --- canned-query execution -------------------------------------------------

def _execute_canned(server: DatabaseRow, tool: McpToolRow, arguments: dict, table_names: list[str]) -> str:
    """Run a tool's ``sql_template`` with bound parameters over the database's (resource-derived) tables."""
    fast = get_connector(_server_dict(server)).build_server(table_names)
    conn = getattr(fast, "_duckdb_conn", None)
    try:
        params = bind_params(tool.input_schema, arguments)
        max_rows = get_settings().mcp_max_result_rows
        return _run_select_params(conn, tool.sql_template, params, max_rows)
    finally:
        if conn is not None:
            conn.close()


def _server_dict(server: DatabaseRow) -> dict:
    return {"id": server.id, "name": server.name, "type": server.type, "uri": server.uri}


# --- pagination (opaque keyset cursor) --------------------------------------

def _page(db, model, database_id, params):
    """Return ``(rows, next_cursor)`` for an active-row listing, keyset-paginated."""
    page_size = get_settings().mcp_list_page_size
    q = db.query(model).filter(model.database_id == database_id, model.deleted_at.is_(None))
    cursor = _decode_cursor(params.get("cursor"))
    if cursor is not None:
        c_created, c_id = cursor
        q = q.filter(or_(model.created_at > c_created,
                         and_(model.created_at == c_created, model.id > c_id)))
    rows = q.order_by(model.created_at, model.id).limit(page_size + 1).all()
    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
    return rows, next_cursor


def _encode_cursor(created_at: datetime, row_id: str) -> str:
    raw = f"{created_at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str | None):
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created, row_id = raw.split("|", 1)
        return datetime.fromisoformat(created), row_id
    except Exception:
        raise _RpcError(INVALID_PARAMS, "Invalid cursor.")


def _with_cursor(result: dict, next_cursor: str | None) -> dict:
    if next_cursor:
        result["nextCursor"] = next_cursor
    return result


def _active_one(db, model, database_id, predicate):
    return (
        db.query(model)
        .filter(model.database_id == database_id, model.deleted_at.is_(None), predicate)
        .first()
    )


# --- JSON-RPC envelope ------------------------------------------------------

class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
