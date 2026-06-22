from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import api_error, render
from data_analysis_agent.api._repository import (
    attached_sources,
    get_session_or_404,
)
from data_analysis_agent.db.models import (
    AgentRunRow,
    DataSourceRow,
    QueryRecordRow,
    SessionDataSourceRow,
    SessionRow,
)
from data_analysis_agent.db.session import get_session

log = structlog.get_logger()
router = APIRouter()


@router.post("/sessions")
def create_session(
    request: Request,
    name: Annotated[str, Form()] = "",
    data_source_ids: Annotated[list[str], Form()] = [],
    session: Session = Depends(get_session),
):
    """Create a session attached to one or more data sources, then redirect to it."""
    if not data_source_ids:
        raise api_error("NO_DATA_SOURCES", "Select at least one data source.")
    sess = SessionRow(name=name.strip() or _default_session_name())
    session.add(sess)
    session.flush()
    _attach_data_sources(session, sess.id, data_source_ids)
    log.info("session.created", session_id=sess.id, ds_count=len(data_source_ids))
    return RedirectResponse(url=f"/sessions/{sess.id}", status_code=303)


@router.get("/sessions/{session_id}")
def session_detail(
    request: Request,
    session_id: str,
    new: str | None = None,
    session: Session = Depends(get_session),
):
    """Render a session's chat view (data sources + query history); disables caching."""
    sess = get_session_or_404(session, session_id)
    records = _session_records(session, session_id)
    response = render(
        request, templates, "session.html",
        sess=sess,
        data_sources=attached_sources(session, session_id),
        records=records,
        new_record_id=new,
        new_record_status=_new_record_status(session, new),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/sessions/{session_id}/delete")
def delete_session(
    request: Request,
    session_id: str,
    session: Session = Depends(get_session),
):
    """Delete a session along with its query records, agent runs, and data-source links."""
    sess = get_session_or_404(session, session_id)
    _delete_query_records(session, session_id)
    session.query(SessionDataSourceRow).filter(
        SessionDataSourceRow.session_id == session_id
    ).delete()
    session.delete(sess)
    log.info("session.deleted", session_id=session_id)
    return RedirectResponse(url="/", status_code=303)


def _default_session_name() -> str:
    """Return a timestamped default session name, e.g. ``Session 2026-06-22 12:30``."""
    return f"Session {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"


def _attach_data_sources(session: Session, session_id: str, data_source_ids: list[str]) -> None:
    """Link the given data sources to a session, rolling back if any is missing."""
    for ds_id in data_source_ids:
        if not session.get(DataSourceRow, ds_id):
            session.rollback()
            raise api_error("NOT_FOUND", f"Data source {ds_id} not found.", status_code=404)
        session.add(SessionDataSourceRow(session_id=session_id, data_source_id=ds_id))


def _session_records(session: Session, session_id: str) -> list[QueryRecordRow]:
    """Return a session's query records, newest first."""
    return (
        session.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .order_by(QueryRecordRow.created_at.desc())
        .all()
    )


def _new_record_status(session: Session, new_id: str | None) -> str | None:
    """Return the status of a just-submitted query record, or ``None``."""
    if not new_id:
        return None
    record = session.get(QueryRecordRow, new_id)
    return record.status if record else None


def _delete_query_records(session: Session, session_id: str) -> None:
    """Delete a session's query records and their associated agent runs."""
    records = session.query(QueryRecordRow).filter(QueryRecordRow.session_id == session_id).all()
    for record in records:
        session.query(AgentRunRow).filter(AgentRunRow.query_record_id == record.id).delete()
        session.delete(record)
