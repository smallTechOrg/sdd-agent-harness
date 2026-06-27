import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import RunRow
from domain.run import RunRequest, RunResponse
from graph.runner import run_agent

router = APIRouter()


@router.post("/runs")
def create_run(req: RunRequest, session: Session = Depends(get_session)) -> dict:
    """Legacy endpoint — kept for backward compatibility. Use POST /sessions/{id}/analyze instead."""
    from db.models import SessionRow
    sess = SessionRow()
    session.add(sess)
    session.flush()
    session_id = sess.id
    session.commit()  # Commit the session row before run_agent opens its own session

    run_id = run_agent(session_id=session_id, question=req.input_text)
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", "Run not found after creation", 500)

    insight_json = None
    if run.insight_json:
        try:
            insight_json = json.loads(run.insight_json)
        except Exception:
            insight_json = None

    chart_specs = None
    if run.chart_specs:
        try:
            chart_specs = json.loads(run.chart_specs)
        except Exception:
            chart_specs = []

    return ok(RunResponse(
        run_id=run.id,
        status=run.status,
        question=run.question,
        sql_query=run.sql_query,
        insight_json=insight_json,
        output_text=run.output_text,
        chart_specs=chart_specs,
        error=run.error_message,
    ).model_dump())


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)

    insight_json = None
    if run.insight_json:
        try:
            insight_json = json.loads(run.insight_json)
        except Exception:
            insight_json = None

    chart_specs = None
    if run.chart_specs:
        try:
            chart_specs = json.loads(run.chart_specs)
        except Exception:
            chart_specs = []

    return ok(RunResponse(
        run_id=run.id,
        status=run.status,
        question=run.question,
        sql_query=run.sql_query,
        insight_json=insight_json,
        output_text=run.output_text,
        chart_specs=chart_specs,
        error=run.error_message,
        created_at=run.created_at.isoformat() if run.created_at else None,
    ).model_dump())
