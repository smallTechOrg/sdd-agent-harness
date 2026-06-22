from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agent.api._common import ok, api_error
from agent.db.session import get_session
from agent.db.models import RunRow
from agent.domain.run import RunRequest, RunResponse
from agent.graph.runner import run_agent

router = APIRouter()


@router.post("/runs")
def create_run(req: RunRequest, session: Session = Depends(get_session)) -> dict:
    run_id = run_agent(req.input_text)
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", "Run not found after creation", 500)
    return ok(RunResponse(run_id=run.id, status=run.status, output_text=run.output_text).model_dump())


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("NOT_FOUND", f"Run {run_id} not found", 404)
    return ok(RunResponse(run_id=run.id, status=run.status, output_text=run.output_text).model_dump())
