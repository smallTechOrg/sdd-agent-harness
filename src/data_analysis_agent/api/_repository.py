from __future__ import annotations

from sqlalchemy.orm import Session

from data_analysis_agent.api._common import api_error
from data_analysis_agent.db.models import (
    DatabaseRow,
    QueryRecordRow,
    SessionDatabaseRow,
    SessionRow,
)


def get_database_or_404(db: Session, database_id: str) -> DatabaseRow:
    """Return an MCP server by id or raise a 404 ``HTTPException``."""
    server = db.get(DatabaseRow, database_id)
    if not server:
        raise api_error("NOT_FOUND", "MCP server not found.", status_code=404)
    return server


def get_session_or_404(db: Session, session_id: str) -> SessionRow:
    """Return a session by id or raise a 404 ``HTTPException``."""
    sess = db.get(SessionRow, session_id)
    if not sess:
        raise api_error("NOT_FOUND", "Session not found.", status_code=404)
    return sess


def attached_databases(db: Session, session_id: str) -> list[DatabaseRow]:
    """Return all MCP servers linked to a session via the join table."""
    links = (
        db.query(SessionDatabaseRow)
        .filter(SessionDatabaseRow.session_id == session_id)
        .all()
    )
    servers = [db.get(DatabaseRow, link.database_id) for link in links]
    return [s for s in servers if s]


def query_count(db: Session, session_id: str) -> int:
    """Return the number of query records submitted within a session."""
    return (
        db.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .count()
    )
