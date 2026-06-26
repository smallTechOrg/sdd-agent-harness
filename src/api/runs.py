from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import RunRow
from domain.run import RunRequest, RunResponse
from graph.runner import run_agent

router = APIRouter()


def _to_response(run: RunRow) -> dict:
    return RunResponse(
        run_id=run.id,
        status=run.status,
        output_text=run.output_text,
        error=run.error_message,
        guard_code=run.guard_code,
        tokens_in=run.tokens_in,
        tokens_out=run.tokens_out,
        cost_usd=run.cost_usd,
        latency_ms=run.latency_ms,
        model=run.model,
        node_trace=run.node_trace,
    ).model_dump()


@router.post("/runs")
def create_run(req: RunRequest, session: Session = Depends(get_session)) -> dict:
    run_id = run_agent(req.input_text, conversation_id=req.conversation_id)
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
