from __future__ import annotations

from sqlalchemy.orm import Session

from data_analysis_agent.api._common import api_error
from data_analysis_agent.db.models import (
    DataSourceRow,
    QueryRecordRow,
    SessionDataSourceRow,
    SessionRow,
)


def get_data_source_or_404(db: Session, datasource_id: str) -> DataSourceRow:
    """Return a data source by id or raise a 404 ``HTTPException``."""
    ds = db.get(DataSourceRow, datasource_id)
    if not ds:
        raise api_error("NOT_FOUND", "Data source not found.", status_code=404)
    return ds


def get_session_or_404(db: Session, session_id: str) -> SessionRow:
    """Return a session by id or raise a 404 ``HTTPException``."""
    sess = db.get(SessionRow, session_id)
    if not sess:
        raise api_error("NOT_FOUND", "Session not found.", status_code=404)
    return sess


def attached_sources(db: Session, session_id: str) -> list[DataSourceRow]:
    """Return all data sources linked to a session via the join table."""
    links = (
        db.query(SessionDataSourceRow)
        .filter(SessionDataSourceRow.session_id == session_id)
        .all()
    )
    sources = [db.get(DataSourceRow, link.data_source_id) for link in links]
    return [s for s in sources if s]


def query_count(db: Session, session_id: str) -> int:
    """Return the number of query records submitted within a session."""
    return (
        db.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .count()
    )
