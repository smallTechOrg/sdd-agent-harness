import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session, create_db_session
from db.models import RunRow
from domain.analysis import AnalysisRequest, AnalysisResponse
from graph.runner import run_agent

router = APIRouter()


@router.post("/analyze")
def analyze(req: AnalysisRequest, session: Session = Depends(get_session)) -> dict:
    try:
        run_id = run_agent(req.dataset_id, req.question)
    except Exception as e:
        raise api_error("ANALYSIS_FAILED", str(e), 500)

    # Use a fresh session to fetch the run — run_agent commits via its own sessions
    with create_db_session() as fresh_session:
        run = fresh_session.get(RunRow, run_id)
        if run is None:
            raise api_error("NOT_FOUND", "Run not found after analysis", 500)

        if run.status == "failed":
            raise api_error("ANALYSIS_FAILED", run.error_message or "Analysis failed", 500)

        labels = json.loads(run.labels_json) if run.labels_json else []
        values = json.loads(run.values_json) if run.values_json else []

        return ok(AnalysisResponse(
            dataset_id=req.dataset_id,
            chart_type=run.chart_type or "bar",
            labels=labels,
            values=[float(v) for v in values],
            summary=run.summary or "",
        ).model_dump())
