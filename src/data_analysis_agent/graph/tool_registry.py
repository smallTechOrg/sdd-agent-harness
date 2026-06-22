from __future__ import annotations

from data_analysis_agent.db.models import (
    DataSourceRow,
    SessionDataSourceRow,
    ToolCapabilityRow,
    ToolRow,
)
from data_analysis_agent.db.session import create_db_session


def load_tool_registry(session_id: str) -> tuple[list[dict], list[dict]]:
    """Load all tools and data sources attached to a session.

    Reads the session's data sources via the join table and, for each, serialises
    the source plus every registered tool and its capabilities into plain dicts
    suitable for storing in ``AgentState``.

    Args:
        session_id: The session whose attached resources should be loaded.

    Returns:
        A ``(tools, data_sources)`` tuple of JSON-serialisable dicts.
    """
    with create_db_session() as db:
        source_ids = _attached_source_ids(db, session_id)
        sources = [_serialize_source(db.get(DataSourceRow, sid)) for sid in source_ids]
        sources = [s for s in sources if s]
        tools = [
            _serialize_tool(tool, _capabilities_for(db, tool.id))
            for sid in source_ids
            for tool in db.query(ToolRow).filter(ToolRow.data_source_id == sid).all()
        ]
        return tools, sources


def _attached_source_ids(db, session_id: str) -> list[str]:
    """Return the data source ids linked to a session via the join table."""
    links = (
        db.query(SessionDataSourceRow)
        .filter(SessionDataSourceRow.session_id == session_id)
        .all()
    )
    return [link.data_source_id for link in links]


def _capabilities_for(db, tool_id: str) -> list[ToolCapabilityRow]:
    """Return all capability rows registered against a tool."""
    return db.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == tool_id).all()


def _serialize_source(ds: DataSourceRow | None) -> dict | None:
    """Convert a data source row into a plain dict, or ``None`` if missing."""
    if ds is None:
        return None
    return {
        "id": ds.id,
        "name": ds.name,
        "type": ds.type,
        "file_path": ds.file_path,
        "parquet_path": ds.parquet_path,
        "column_names": ds.column_names,
        "row_count": ds.row_count,
    }


def _serialize_tool(tool: ToolRow, capabilities: list[ToolCapabilityRow]) -> dict:
    """Convert a tool row and its capabilities into a plain dict for AgentState."""
    return {
        "name": tool.name,
        "type": tool.type,
        "description": tool.description,
        "config": tool.config,
        "data_source_id": tool.data_source_id,
        "capabilities": [
            {
                "name": c.name,
                "description": c.description,
                "parameter_schema": c.parameter_schema,
            }
            for c in capabilities
        ],
    }
