"""Run status routes (Phase 2).

The boilerplate `POST /runs` (single-arg `run_agent(input_text)`) is retired —
the canonical analysis route is `POST /ask`. These read-only routes back live
progress polling against `query_runs`:

- `GET /runs/current` — the most recent run for the live progress bar.
- `GET /runs/{run_id}` — one run's status / step counts.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from config.settings import get_settings
from db.session import get_session
from db.models import QueryRunRow

router = APIRouter()


@router.get("/runs/current")
def current_run(session: Session = Depends(get_session)) -> dict:
    """Most recent run for live polling; status `idle` when there are none."""
    settings = get_settings()
    max_iterations = settings.max_iterations
    row = session.execute(
        select(QueryRunRow).order_by(QueryRunRow.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if row is None:
        return ok(
            {
                "run_id": None,
                "status": "idle",
                "iteration_count": 0,
                "max_iterations": max_iterations,
            }
        )
    return ok(
        {
            "run_id": row.id,
            "status": row.status,
            "iteration_count": row.iteration_count,
            "max_iterations": max_iterations,
        }
    )


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(QueryRunRow, run_id)
    if row is None:
        raise api_error("not_found", f"Run {run_id} not found", 404)
    return ok(
        {
            "run_id": row.id,
            "status": row.status,
            "iteration_count": row.iteration_count,
            "tokens_input": row.tokens_input,
            "tokens_output": row.tokens_output,
            "answer": row.answer,
            "error_message": row.error_message,
            "dataset_ids": row.dataset_ids_json or [],
        }
    )
