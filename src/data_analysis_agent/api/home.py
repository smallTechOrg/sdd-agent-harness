from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import render
from data_analysis_agent.api._repository import attached_sources, query_count
from data_analysis_agent.db.models import DataSourceRow, SessionRow
from data_analysis_agent.db.session import get_session

router = APIRouter()


@router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    """Render the home page listing all data sources and sessions."""
    sources = session.query(DataSourceRow).order_by(DataSourceRow.created_at.desc()).all()
    sessions = session.query(SessionRow).order_by(SessionRow.updated_at.desc()).all()
    session_sources, session_query_counts = _session_overview(session, sessions)
    return render(
        request, templates, "home.html",
        sources=sources,
        all_sessions=sessions,
        session_sources=session_sources,
        session_query_counts=session_query_counts,
    )


def _session_overview(
    db: Session, sessions: list[SessionRow]
) -> tuple[dict[str, list[DataSourceRow]], dict[str, int]]:
    """Build per-session attached-source lists and question counts for the home view.

    Args:
        db: The active database session.
        sessions: The sessions to summarise.

    Returns:
        A ``(sources_by_session, count_by_session)`` tuple keyed by session id.
    """
    sources_by_session = {s.id: attached_sources(db, s.id) for s in sessions}
    count_by_session = {s.id: query_count(db, s.id) for s in sessions}
    return sources_by_session, count_by_session
