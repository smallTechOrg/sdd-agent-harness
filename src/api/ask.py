"""Ask endpoint: run the agent over one dataset and return narrative + table."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from domain.analysis import AskRequest, AskResponse

router = APIRouter()


def _classify_error(error_message: str) -> tuple[str, str, int]:
    """Map an agent error message to (code, message, http_status).

    400 -> bad/invalid SQL or bad request; 502 -> Gemini/LLM; 500 -> DuckDB.
    """
    msg = (error_message or "").lower()
    if "invalid sql" in msg or "select" in msg and "llm" not in msg and "duckdb" not in msg:
        return "INVALID_SQL", error_message, 400
    if "llm" in msg or "gemini" in msg:
        return "LLM_UNAVAILABLE", error_message, 502
    if "duckdb" in msg or "execution failed" in msg or "schema profiling" in msg:
        return "DUCKDB_ERROR", error_message, 500
    # Unknown agent failure -> 500.
    return "AGENT_ERROR", error_message or "Agent run failed", 500


@router.post("/ask")
def ask(req: AskRequest, db: Session = Depends(get_session)) -> dict:
    from graph.runner import run_agent

    if not req.question or not req.question.strip():
        raise api_error("BAD_REQUEST", "Question must not be empty", 400)

    try:
        result = run_agent(
            dataset_id=req.dataset_id,
            question=req.question,
            session_id=req.session_id,
            db_session=db,
        )
    except ValueError as exc:
        # Unknown dataset / bad input — no audit row possible (no run started).
        raise api_error("BAD_REQUEST", str(exc), 400)

    if result.get("status") == "failed":
        # Audit row already written as failed by the runner.
        code, message, status = _classify_error(result.get("error"))
        raise api_error(code, message, status)

    payload = AskResponse(
        run_id=result["run_id"],
        narrative=result.get("narrative"),
        sql=result.get("sql"),
        columns=result.get("columns", []),
        rows=result.get("rows", []),
        row_count=result.get("row_count", 0),
        duration_ms=result.get("duration_ms", 0),
        status=result["status"],
    )
    return ok(payload.model_dump())
