from __future__ import annotations

import threading
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api._common import api_error
from data_analysis_agent.api._repository import get_session_or_404
from data_analysis_agent.db.models import QueryRecordRow, SessionRow
from data_analysis_agent.db.session import create_db_session, get_session

log = structlog.get_logger()
router = APIRouter()


@router.post("/sessions/{session_id}/query")
def submit_query(
    request: Request,
    session_id: str,
    question: str = Form(...),
    session: Session = Depends(get_session),
):
    """Record a question, launch the pipeline in the background, redirect for polling."""
    text = question.strip()
    if not text:
        raise api_error("EMPTY_QUESTION", "Question cannot be empty.")
    get_session_or_404(session, session_id)
    query_record_id = _create_query_record(session, session_id, text)
    _start_pipeline(query_record_id, session_id, text)
    log.info("query.submitted", query_record_id=query_record_id, session_id=session_id)
    return RedirectResponse(url=f"/sessions/{session_id}?new={query_record_id}", status_code=303)


@router.get("/sessions/{session_id}/query/{qr_id}/status")
def query_status(
    session_id: str,
    qr_id: str,
    session: Session = Depends(get_session),
):
    """Return the JSON ``{status, error}`` of a single query record for client polling."""
    record = session.get(QueryRecordRow, qr_id)
    if not record or record.session_id != session_id:
        raise api_error("NOT_FOUND", "Query not found.", status_code=404)
    return JSONResponse({"status": record.status, "error": record.error_message})


def _create_query_record(session: Session, session_id: str, question: str) -> str:
    """Persist a pending query record, touch the session timestamp, and commit."""
    record = QueryRecordRow(session_id=session_id, question=question)
    session.add(record)
    session.flush()
    record_id = record.id
    sess = session.get(SessionRow, session_id)
    if sess:
        sess.updated_at = datetime.now(timezone.utc)
    session.commit()
    return record_id


def _start_pipeline(query_record_id: str, session_id: str, question: str) -> None:
    """Launch the agent pipeline on a daemon thread so the request returns at once."""
    thread = threading.Thread(
        target=_run_pipeline_background,
        args=(query_record_id, session_id, question),
        daemon=True,
    )
    thread.start()


def _run_pipeline_background(query_record_id: str, session_id: str, question: str) -> None:
    """Execute the agent pipeline off the request thread, recording any failure."""
    try:
        from data_analysis_agent.graph.runner import run_pipeline
        run_pipeline(query_record_id=query_record_id, session_id=session_id, question=question)
    except Exception as exc:
        log.error("query.background_pipeline_error", query_record_id=query_record_id, error=str(exc))
        _mark_query_failed(query_record_id, str(exc))


def _mark_query_failed(query_record_id: str, error: str) -> None:
    """Best-effort: flag a still-pending query record as failed after a crash."""
    try:
        with create_db_session() as db:
            record = db.get(QueryRecordRow, query_record_id)
            if record and record.status == "pending":
                record.status = "failed"
                record.error_message = error
    except Exception:
        pass
