"""POST /ask — ask a plain-English question about a local dataset.

Runs the agent graph (real Gemini) which produces a plain-English answer and a
chart spec while keeping raw rows local. Only schema + aggregates reach the LLM
(enforced inside the graph). This route reads back the persisted QuestionRow and
returns the contracted envelope.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import DatasetRow, QuestionRow
from db.session import get_session
from domain.ask import AskRequest, AskResponse
from graph.runner import run_agent

router = APIRouter()


def _is_llm_error(message: str | None) -> bool:
    """Classify a stored/raised error as an LLM failure vs. local compute."""
    if not message:
        return False
    text = message.lower()
    return (
        "llm_unavailable" in text
        or "gemini" in text
        or "llm" in text
        or "model" in text
    )


@router.post("/ask")
def ask(req: AskRequest, session: Session = Depends(get_session)) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise api_error("BAD_REQUEST", "Please enter a question.", 400)

    dataset = session.get(DatasetRow, req.dataset_id)
    if dataset is None:
        raise api_error("BAD_REQUEST", "That dataset doesn't exist.", 400)

    # Run the agent graph. The runner creates + persists the QuestionRow itself.
    try:
        question_id = run_agent(req.dataset_id, question)
    except Exception as exc:  # noqa: BLE001
        if _is_llm_error(str(exc)):
            raise api_error("LLM_UNAVAILABLE", "Couldn't reach the model — try again", 502)
        raise api_error("COMPUTE_FAILED", f"Local compute failed: {exc}", 500)

    q = session.get(QuestionRow, question_id)
    if q is None:
        raise api_error("COMPUTE_FAILED", "The question result wasn't found after the run.", 500)

    if q.status == "failed":
        if _is_llm_error(q.error_message):
            raise api_error("LLM_UNAVAILABLE", "Couldn't reach the model — try again", 502)
        raise api_error("COMPUTE_FAILED", q.error_message or "Local compute failed.", 500)

    chart_spec = json.loads(q.chart_spec) if q.chart_spec else None
    response = AskResponse(
        question_id=q.id,
        answer_text=q.answer_text,
        chart_spec=chart_spec,
        status="completed",
    )
    return ok(response.model_dump())
