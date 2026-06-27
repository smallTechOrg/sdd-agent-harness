"""Shared view-model builders for the single-page shell.

`/`, `/sessions/{id}` and `/database/{id}` all render the same ``index.html`` with a different active
entity; :func:`spa_context` assembles the common context (servers + sessions sidebars) plus whichever
entity is active. Every dataset URI is rendered credential-free via :meth:`DatasetURI.display`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from data_analysis_agent.api._pagination import page_window
from data_analysis_agent.api._repository import attached_databases, query_count
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.tools.connectors.base import DATABASE_TYPES
from data_analysis_agent.db.models import (
    McpPromptRow,
    McpResourceRow,
    DatabaseRow,
    McpToolRow,
    QueryRecordRow,
    SessionRow,
)
from data_analysis_agent.tools.connectors.uri import DatasetURI


def _active_count(db: Session, model, database_id: str) -> int:
    return (
        db.query(model)
        .filter(model.database_id == database_id, model.deleted_at.is_(None))
        .count()
    )


def _active_rows(db: Session, model, database_id: str) -> list:
    return (
        db.query(model)
        .filter(model.database_id == database_id, model.deleted_at.is_(None))
        .order_by(model.created_at, model.id)
        .all()
    )


def _entity_tables(resources: list) -> list[dict]:
    """Project the entity (non-schema) resources to table dicts (the per-table schema source of truth).

    Each entity resource's ``content`` is ``{table, columns, row_count}``; columns are the table's schema.
    """
    tables: list[dict] = []
    for r in resources:
        if r.kind == "schema":
            continue
        content = r.content or {}
        columns = content.get("columns") or []
        tables.append({
            "table_name": content.get("table") or r.name,
            "column_names": [c.get("name") for c in columns],
            "schema": columns,
            "row_count": content.get("row_count"),
        })
    return tables


def server_card_view(db: Session, server: DatabaseRow) -> dict:
    """A credential-free summary of one database for the sidebar / Databases card."""
    resources = _active_rows(db, McpResourceRow, server.id)
    tables = _entity_tables(resources)
    return {
        "id": server.id,
        "name": server.name,
        "title": server.title,
        "type": server.type,
        "is_parquet": (server.type or "").lower() == "parquet",
        "uri_display": DatasetURI(server.uri).display(),
        "version": server.version,
        "table_count": len(tables),
        "total_rows": sum(t.get("row_count") or 0 for t in tables),
        "tool_count": _active_count(db, McpToolRow, server.id),
        "resource_count": len(resources),
        "prompt_count": _active_count(db, McpPromptRow, server.id),
        "last_sync_status": server.last_sync_status,
        "last_synced_at": server.last_synced_at,
        "connection_error": server.connection_error,
    }


def session_card_view(db: Session, sess: SessionRow, active_id: str | None) -> dict:
    """A summary of one session for the sidebar list."""
    servers = attached_databases(db, sess.id)
    return {
        "id": sess.id,
        "name": sess.name or "Untitled session",
        "server_names": [s.name for s in servers],
        "query_count": query_count(db, sess.id),
        "created_at": sess.created_at,
        "updated_at": sess.updated_at,
        "is_active": sess.id == active_id,
    }


def _active_query(db: Session, model, database_id: str):
    """The base query for a server's active (non-soft-deleted) child rows, in stable list order."""
    return (
        db.query(model)
        .filter(model.database_id == database_id, model.deleted_at.is_(None))
        .order_by(model.created_at, model.id)
    )


def paged_capability(db: Session, model, database_id: str, offset: int) -> tuple[list, bool]:
    """One ``ui_page_size`` window of a server's active tool/resource/prompt rows (for Load-more)."""
    return page_window(_active_query(db, model, database_id),
                       offset=offset, limit=get_settings().ui_page_size)


def server_detail_view(db: Session, server: DatabaseRow) -> dict:
    """Full detail for the Database tab: metadata, physical tables, schema, and the first page of each
    child list. The EER diagram is fed from ALL entity resources (a diagram, never paginated); the
    capability lists render the first page + a ``*_has_more`` flag driving a Load-more button."""
    all_resources = _active_rows(db, McpResourceRow, server.id)  # full set: EER + schema + total count
    schema_res = next((r for r in all_resources if r.kind == "schema"), None)
    tools, tools_more = paged_capability(db, McpToolRow, server.id, 0)
    resources, resources_more = paged_capability(db, McpResourceRow, server.id, 0)
    prompts, prompts_more = paged_capability(db, McpPromptRow, server.id, 0)
    return {
        "id": server.id,
        "name": server.name,
        "title": server.title,
        "description": server.description,
        "type": server.type,
        "is_parquet": (server.type or "").lower() == "parquet",
        "uri_display": DatasetURI(server.uri).display(),
        "version": server.version,
        "last_sync_status": server.last_sync_status,
        "last_synced_at": server.last_synced_at,
        "connection_error": server.connection_error,
        "tables": _entity_tables(all_resources),        # per-table schema from the entity resources (full)
        "dataset_schema": (schema_res.content if schema_res else {}),  # from the schema resource
        "tools": tools, "tools_has_more": tools_more,
        "tool_count": _active_count(db, McpToolRow, server.id),
        "resources": resources, "resources_has_more": resources_more,
        "resource_count": len(all_resources),
        "prompts": prompts, "prompts_has_more": prompts_more,
        "prompt_count": _active_count(db, McpPromptRow, server.id),
    }


def paged_sessions(db: Session, offset: int, active_id: str | None) -> tuple[list[dict], bool]:
    """One ``ui_page_size`` window of session cards, most-recently-updated first (for the sidebar)."""
    q = db.query(SessionRow).order_by(SessionRow.updated_at.desc())
    rows, has_more = page_window(q, offset=offset, limit=get_settings().ui_page_size)
    return [session_card_view(db, s, active_id) for s in rows], has_more


def paged_databases(db: Session, offset: int) -> tuple[list[dict], bool]:
    """One ``ui_page_size`` window of database cards, newest first (for the Databases card)."""
    q = db.query(DatabaseRow).order_by(DatabaseRow.created_at.desc())
    rows, has_more = page_window(q, offset=offset, limit=get_settings().ui_page_size)
    return [server_card_view(db, s) for s in rows], has_more


def paged_queries(db: Session, session_id: str, offset: int) -> tuple[list[QueryRecordRow], bool]:
    """One window of a session's query records for the chat thread.

    Windows are taken newest-first (``offset`` counts back from the latest), but each window is returned
    **chronological** (oldest→newest) for display, so the freshest turn sits at the bottom by the ask
    form. ``has_more`` means OLDER turns exist beyond this window (revealed by scrolling up)."""
    q = (
        db.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .order_by(QueryRecordRow.created_at.desc(), QueryRecordRow.id.desc())
    )
    rows, has_more = page_window(q, offset=offset, limit=get_settings().ui_page_size)
    return list(reversed(rows)), has_more


def spa_context(
    db: Session,
    *,
    active_tab: str = "analyse",
    active_session: SessionRow | None = None,
    active_server: DatabaseRow | None = None,
    new_record_id: str | None = None,
) -> dict:
    """Assemble the shared single-page context: server + session sidebars (first page) and the active
    entity. The sidebars/lists render their first page + a ``*_has_more`` flag driving Load-more."""
    active_session_id = active_session.id if active_session else None
    sessions, sessions_more = paged_sessions(db, 0, active_session_id)
    servers, servers_more = paged_databases(db, 0)
    ctx: dict = {
        "servers": servers,
        "servers_has_more": servers_more,
        "server_total": db.query(DatabaseRow).count(),
        "sessions": sessions,
        "sessions_has_more": sessions_more,
        "page_size": get_settings().ui_page_size,
        "active_tab": active_tab,
        "active_session": None,
        "active_server": None,
        "new_record_id": new_record_id,
        "new_record_status": None,
        "llm_model": get_settings().llm_model,
        "database_types": [{"value": v, "label": label, "external": ext, "hint": hint}
                           for v, label, ext, hint in DATABASE_TYPES],
    }
    if active_session is not None:
        records, older_has_more = paged_queries(db, active_session.id, 0)
        ctx["active_session"] = {
            "id": active_session.id,
            "name": active_session.name or "Untitled session",
            "servers": attached_databases(db, active_session.id),
            "records": records,
            "older_has_more": older_has_more,
        }
        if new_record_id:
            rec = db.get(QueryRecordRow, new_record_id)
            ctx["new_record_status"] = rec.status if rec else None
    if active_server is not None:
        ctx["active_server"] = server_detail_view(db, active_server)
    return ctx
