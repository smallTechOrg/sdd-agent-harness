from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import api_error, render
from data_analysis_agent.api._repository import get_session_or_404
from data_analysis_agent.api._view import spa_context
from data_analysis_agent.db.models import (
    AgentRunRow,
    DatabaseRow,
    QueryRecordRow,
    SessionDatabaseRow,
    SessionRow,
)
from data_analysis_agent.db.session import get_session
from data_analysis_agent.tools.mcp.pool import get_manager

log = structlog.get_logger()
router = APIRouter()


@router.post("/sessions")
def create_session(
    request: Request,
    name: Annotated[str, Form()] = "",
    database_ids: Annotated[list[str], Form()] = [],
    session: Session = Depends(get_session),
):
    """Create a session attached to one or more MCP servers, then redirect to it."""
    if not database_ids:
        raise api_error("NO_SERVERS", "Select at least one MCP server.")
    sess = SessionRow(name=name.strip() or _default_session_name())
    session.add(sess)
    session.flush()
    _attach_servers(session, sess.id, database_ids)
    session_id = sess.id
    log.info("session.created", session_id=session_id, server_count=len(database_ids))
    session.commit()  # make the links visible before warming the pool
    _warm_pool(session_id)
    return RedirectResponse(url=f"/sessions/{session_id}", status_code=303)


@router.get("/sessions/{session_id}")
def session_detail(
    request: Request,
    session_id: str,
    new: str | None = None,
    session: Session = Depends(get_session),
):
    """Render the single-page shell with this session active (Analyse tab); disables caching."""
    sess = get_session_or_404(session, session_id)
    ctx = spa_context(session, active_tab="analyse", active_session=sess, new_record_id=new)
    return render(request, templates, "index.html", **ctx)  # render() marks the shell no-store


@router.post("/sessions/{session_id}/delete")
def delete_session(
    request: Request,
    session_id: str,
    session: Session = Depends(get_session),
):
    """Delete a session along with its query records, agent runs, and data-source links."""
    sess = get_session_or_404(session, session_id)
    get_manager().close(session_id)  # release the session's MCP pool / DuckDB connections
    _delete_query_records(session, session_id)
    session.query(SessionDatabaseRow).filter(
        SessionDatabaseRow.session_id == session_id
    ).delete()
    session.delete(sess)
    log.info("session.deleted", session_id=session_id)
    return RedirectResponse(url="/", status_code=303)


def _default_session_name() -> str:
    """Return a timestamped default session name, e.g. ``Session 2026-06-22 12:30``."""
    return f"Session {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"


def _warm_pool(session_id: str) -> None:
    """Best-effort: build the session's MCP pool now so its first query is fast.

    Failures (e.g. a transient build error) are logged and ignored — the pool is rebuilt
    lazily on the first query regardless.
    """
    try:
        asyncio.run(get_manager().acquire(session_id))
    except Exception as exc:
        log.warning("session.warm_failed", session_id=session_id, error=str(exc))


def _attach_servers(session: Session, session_id: str, database_ids: list[str]) -> None:
    """Link the given MCP servers to a session, rolling back if any is missing."""
    for database_id in database_ids:
        if not session.get(DatabaseRow, database_id):
            session.rollback()
            raise api_error("NOT_FOUND", f"MCP server {database_id} not found.", status_code=404)
        session.add(SessionDatabaseRow(session_id=session_id, database_id=database_id))


def _delete_query_records(session: Session, session_id: str) -> None:
    """Delete a session's query records and their associated agent runs."""
    records = session.query(QueryRecordRow).filter(QueryRecordRow.session_id == session_id).all()
    for record in records:
        session.query(AgentRunRow).filter(AgentRunRow.query_record_id == record.id).delete()
        session.delete(record)
