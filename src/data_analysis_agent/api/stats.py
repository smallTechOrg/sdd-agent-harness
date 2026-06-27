from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import DatabaseRow, McpResourceRow, QueryRecordRow
from data_analysis_agent.db.session import get_session

router = APIRouter()


@router.get("/stats/daily")
def daily_stats(session: Session = Depends(get_session)):
    """Token/cost usage for the sidebar widget: today's totals, the last query, and storage."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day = (
        session.query(
            func.coalesce(func.sum(QueryRecordRow.input_tokens), 0),
            func.coalesce(func.sum(QueryRecordRow.output_tokens), 0),
            func.coalesce(func.sum(QueryRecordRow.estimated_cost_usd), 0.0),
            func.count(QueryRecordRow.id),
        )
        .filter(QueryRecordRow.created_at >= today)
        .one()
    )
    last = (
        session.query(QueryRecordRow)
        .filter(QueryRecordRow.status == "completed")
        .order_by(QueryRecordRow.created_at.desc())
        .first()
    )
    server_count = session.query(DatabaseRow).count()
    # Total rows across all databases' entity resources (per-table row_count lives in their content).
    entities = (
        session.query(McpResourceRow)
        .filter(McpResourceRow.deleted_at.is_(None), McpResourceRow.kind != "schema")
        .all()
    )
    total_rows = sum((r.content or {}).get("row_count") or 0 for r in entities)
    return JSONResponse({"data": {
        "model": get_settings().llm_model,
        "tokens_input": int(day[0]),
        "tokens_output": int(day[1]),
        "cost_usd": round(float(day[2]), 6),
        "query_count": int(day[3]),
        "last_input": int(last.input_tokens or 0) if last else 0,
        "last_output": int(last.output_tokens or 0) if last else 0,
        "last_cost": round(float(last.estimated_cost_usd or 0.0), 6) if last else 0.0,
        "server_count": server_count,
        "total_rows": total_rows,
    }})
