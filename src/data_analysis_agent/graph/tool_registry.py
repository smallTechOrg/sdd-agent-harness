from __future__ import annotations

from data_analysis_agent.db.models import DataSourceRow, SessionDataSourceRow
from data_analysis_agent.db.session import create_db_session
from data_analysis_agent.tools.table_naming import sql_table_name


def load_sources_for_session(session_id: str) -> list[dict]:
    """Load the data sources attached to a session as JSON-serialisable dicts.

    Each dict carries everything needed to build the source's MCP server and the
    planning prompt: the computed ``table_name``, the Parquet path, the schema, and
    the persisted LLM-generated descriptions. Tools themselves are not loaded from the
    DB — they are served at runtime by the per-source MCP server.

    Args:
        session_id: The session whose attached sources should be loaded.

    Returns:
        A list of serialised data-source dicts (empty if the session has none).
    """
    with create_db_session() as db:
        source_ids = _attached_source_ids(db, session_id)
        rows = [db.get(DataSourceRow, sid) for sid in source_ids]
        return [_serialize_source(row) for row in rows if row is not None]


def _attached_source_ids(db, session_id: str) -> list[str]:
    """Return the data source ids linked to a session via the join table."""
    links = (
        db.query(SessionDataSourceRow)
        .filter(SessionDataSourceRow.session_id == session_id)
        .all()
    )
    return [link.data_source_id for link in links]


def _serialize_source(ds: DataSourceRow) -> dict:
    """Convert a data source row into a plain dict (incl. the computed table name)."""
    return {
        "id": ds.id,
        "name": ds.name,
        "table_name": sql_table_name(ds.name),
        "file_path": ds.file_path,
        "parquet_path": ds.parquet_path,
        "column_names": ds.column_names,
        "row_count": ds.row_count,
        "tool_description": ds.tool_description,
        "capability_description": ds.capability_description,
    }
