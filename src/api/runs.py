import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import RunRow
from domain.run import RunRequest, RunResponse
from graph.runner import run_agent

router = APIRouter()


def _parse_result_table(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_response(run: RunRow) -> dict:
    result_table = _parse_result_table(run.result_table)
    return RunResponse(
        run_id=run.id,
        status=run.status,
        mode=getattr(run, "mode", "pandas"),
        answer=run.answer,
        explanation=run.explanation,
        generated_code=run.generated_code,
        result_table=result_table,
        truncated=False,
        error=run.error_message,
    ).model_dump()


@router.post("/runs")
def create_run(req: RunRequest, session: Session = Depends(get_session)) -> dict:
    run_id = run_agent(req.csv_text, req.question, mode=req.mode)
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", "Run not found after creation", 500)
    return ok(_to_response(run))


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)
    return ok(_to_response(run))
