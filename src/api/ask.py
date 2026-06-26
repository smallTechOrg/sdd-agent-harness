"""`POST /ask` — run a single-dataset analysis (Phase 2).

Phase-2 scope: single-dataset Q&A with NO sessions and NO pre-flight
clarification/selector (those are Phase 3). The route validates the question,
resolves the dataset id(s) explicitly, calls `run_agent`, renders the Markdown
answer to HTML, and returns the `type:"answer"` payload `spec/api.md` defines.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from markdown_it import MarkdownIt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import DatasetRow
from db.session import get_session
from domain.ask import AskRequest
from graph.runner import run_agent

router = APIRouter()

_md = MarkdownIt()


def _resolve_dataset_ids(req: AskRequest) -> list[str]:
    """Resolve the dataset ids from `dataset_ids` (preferred) or `dataset_id`."""
    if req.dataset_ids:
        return [d for d in req.dataset_ids if d]
    if req.dataset_id:
        return [req.dataset_id]
    return []


@router.post("/ask")
def ask(req: AskRequest, session: Session = Depends(get_session)) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise api_error("empty_question", "Question must not be empty.", 400)

    dataset_ids = _resolve_dataset_ids(req)

    if dataset_ids:
        # An explicit dataset was requested — a missing one is a 404 (more specific
        # than the global "no datasets" guard).
        for dataset_id in dataset_ids:
            if session.get(DatasetRow, dataset_id) is None:
                raise api_error("not_found", f"Dataset {dataset_id} not found", 404)
    else:
        # No explicit dataset and Phase-2 has no selector — if none exist at all,
        # that's the "no datasets uploaded" case; otherwise the user must pick one.
        dataset_count = session.execute(
            select(func.count()).select_from(DatasetRow)
        ).scalar_one()
        if dataset_count == 0:
            raise api_error("no_datasets", "No datasets uploaded yet. Upload a file first.", 400)
        raise api_error("no_datasets", "Specify a dataset to ask about.", 400)

    result = run_agent(question, dataset_ids)

    answer_markdown = result.get("answer") or ""
    answer_html = _md.render(answer_markdown) if answer_markdown else ""
    datasets_used = result.get("dataset_ids") or dataset_ids

    return ok(
        {
            "type": "answer",
            "run_id": result["run_id"],
            "session_id": None,  # sessions are Phase 3
            "dataset_ids": dataset_ids,
            "derived_dataset_ids": [],  # derived datasets are Phase 4
            "datasets_used": datasets_used,
            "selector_reasoning": result.get("selector_reasoning"),
            "answer_markdown": answer_markdown,
            "answer_html": answer_html,
            "iteration_count": result.get("iteration_count", 0),
            "tokens_input": result.get("tokens_input", 0),
            "tokens_output": result.get("tokens_output", 0),
            "status": result.get("status", "completed"),
            "is_best_effort": result.get("is_best_effort", False),
            "steps": result.get("action_history") or [],
            "suggested_questions": [],  # Phase 3
            "prompt_breakdown": {},  # Phase 3
        }
    )
