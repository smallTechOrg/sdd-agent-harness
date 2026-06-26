"""Run a single analysis through the ReAct graph.

Phase 3 signature: adds sessions (multi-turn), pre-flight (C26 clarification +
C19 selector), follow-up suggestions, and the C29 prompt_breakdown. Pre-flight
runs ONLY when the datasets are NOT explicit (`run_selector=True`) — explicit
`dataset_ids` (the Phase-2 direct path) skip BOTH clarification and the selector,
per `spec/agent.md` ("Pre-flight ... is SKIPPED when explicit dataset_ids are
supplied").

The runner creates the `query_runs` row, runs pre-flight, invokes the compiled
`agentic_ai` graph, persists the result, calls `generate_suggestions`, and
returns the `/ask` payload. It does NOT commit/push and is provider-agnostic
(all LLM calls go through `LLMClient`).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import get_settings
from db.models import DatasetRow, QueryRunRow
from db.session import create_db_session
from graph.agent import agentic_ai
from graph.nodes import _safe_memory_block
from graph.preflight import check_clarification, select_datasets
from graph.state import AgentState
from graph.suggestions import generate_suggestions
from observability.events import get_logger

logger = get_logger("graph.runner")


def _estimate_tokens(text: str) -> int:
    """~4 chars/token heuristic (matches nodes.py / suggestions.py)."""
    return max(1, len(text or "") // 4)


def _uploads_dir() -> Path:
    """`uploads/` at the repo root (two levels up from src/graph/)."""
    return Path(__file__).resolve().parent.parent.parent / "uploads"


def _candidate_schemas(dataset_ids: list[str]) -> tuple[list[dict], str]:
    """Build a compact schema view of each candidate dataset for pre-flight.

    Returns `(schemas, schemas_text)`:
    - `schemas`: list of `{"id", "filename", "columns", "notes"}` dicts for
      `select_datasets`.
    - `schemas_text`: a human-readable block for `check_clarification`.

    Columns come from the cheap `datasets.columns_json` metadata (no file read).
    Falls back to a header-only Parquet/CSV peek if the column list is missing.
    """
    schemas: list[dict] = []
    text_parts: list[str] = []

    with create_db_session() as session:
        for dataset_id in dataset_ids:
            row = session.get(DatasetRow, dataset_id)
            if row is None:
                continue
            columns = list(row.columns_json or [])
            if not columns:
                columns = _peek_columns(dataset_id)
            filename = row.filename or f"{dataset_id}.csv"
            notes = (row.context or "").strip()
            schemas.append(
                {"id": dataset_id, "filename": filename, "columns": columns, "notes": notes}
            )
            cols_text = ", ".join(str(c) for c in columns)
            block = f"- {filename} (id {dataset_id}): columns [{cols_text}]"
            if notes:
                block += f"; notes: {notes[:200]}"
            text_parts.append(block)

    return schemas, "\n".join(text_parts)


def _peek_columns(dataset_id: str) -> list[str]:
    """Cheap column-name peek from the data file (header only). Empty on failure."""
    base = _uploads_dir()
    parquet_path = base / f"{dataset_id}.parquet"
    csv_path = base / f"{dataset_id}.csv"
    try:
        if parquet_path.exists():
            return list(pd.read_parquet(parquet_path, columns=None).columns)
        if csv_path.exists():
            return list(pd.read_csv(csv_path, nrows=0).columns)
    except Exception as exc:  # noqa: BLE001 — peek is best-effort
        logger.warning("schema_peek_failed", dataset_id=dataset_id, error=str(exc))
    return []


def _build_prompt_breakdown(
    *,
    question: str,
    conversation_history: list[dict],
    dataset_context: str,
    memory_block: str,
    action_history: list[dict],
    tokens_input: int,
) -> dict[str, int]:
    """C29: measure each prompt component with the char/4 heuristic (approximate).

    Returns a dict of estimated token contributions per component plus the run's
    accumulated `total_prompt` (the real summed input tokens from the loop).
    """
    history_text = "\n".join(
        f"Q: {t.get('question', '')}\nA: {t.get('answer', '')}" for t in conversation_history
    )
    action_text = "\n".join(
        f"{s.get('action', '')} -> {s.get('result', '')}" for s in action_history
    )
    return {
        "total_prompt": int(tokens_input),
        "history": _estimate_tokens(history_text),
        "dataset_schemas": _estimate_tokens(dataset_context or ""),
        "memory": _estimate_tokens(memory_block or ""),
        "action_history": _estimate_tokens(action_text),
        "system_overhead": _estimate_tokens(question or "") + 64,
    }


def run_agent(
    question: str,
    dataset_ids: list[str],
    *,
    session_id: str | None = None,
    conversation_history: list[dict] | None = None,
    skip_clarification: bool = False,
    run_selector: bool = False,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Run a single analysis; return the `/ask` payload.

    Pre-flight (clarification + selector) runs ONLY when `run_selector=True`
    (datasets NOT explicit). With explicit ids (`run_selector=False`, the default
    Phase-2 path) BOTH pre-flight calls are skipped.

    Returns either:
    - a clarification short-circuit (no graph run):
      `{"type":"clarification","run_id","clarification_question","session_id"}`
    - an answer:
      `{"type":"answer", run_id, status, answer, iteration_count, tokens_input,
        tokens_output, action_history, charts, dataset_ids, is_best_effort,
        selector_reasoning, suggested_questions, prompt_breakdown, session_id}`
    """
    settings = get_settings()
    cap = max_iterations if max_iterations is not None else settings.max_iterations
    candidate_ids = [d for d in (dataset_ids or []) if d]
    conversation_history = conversation_history or []

    selector_reasoning: str | None = None
    resolved_ids = list(candidate_ids)

    # ------------------------------------------------------------------ #
    # Pre-flight (only when datasets are NOT explicit).
    # ------------------------------------------------------------------ #
    if run_selector:
        schemas, schemas_text = _candidate_schemas(candidate_ids)

        # 1. C26 clarification — short-circuit on an ambiguous question.
        if not skip_clarification:
            clarification = check_clarification(question, schemas_text)
            if clarification:
                with create_db_session() as session:
                    row = QueryRunRow(
                        dataset_id=candidate_ids[0] if candidate_ids else None,
                        session_id=session_id,
                        question=question,
                        status="clarification",
                        answer=clarification,
                        dataset_ids_json=list(candidate_ids),
                        iteration_count=0,
                        tokens_input=0,
                        tokens_output=0,
                    )
                    session.add(row)
                    session.flush()
                    clar_run_id = row.id
                logger.info("clarification_returned", run_id=clar_run_id, session_id=session_id)
                return {
                    "type": "clarification",
                    "run_id": clar_run_id,
                    "clarification_question": clarification,
                    "session_id": session_id,
                }

        # 2. C19 selector — pick the minimal dataset subset (fall back to all).
        resolved_ids, selector_reasoning = select_datasets(question, schemas, candidate_ids)

    # ------------------------------------------------------------------ #
    # Create the query_runs row (status=running) with the FINAL ids.
    # ------------------------------------------------------------------ #
    with create_db_session() as session:
        row = QueryRunRow(
            dataset_id=resolved_ids[0] if resolved_ids else None,
            session_id=session_id,
            question=question,
            status="running",
            dataset_ids_json=list(resolved_ids),
            selector_reasoning=selector_reasoning,
            iteration_count=0,
            tokens_input=0,
            tokens_output=0,
        )
        session.add(row)
        session.flush()
        run_id = row.id

    logger.info(
        "run_start",
        run_id=run_id,
        datasets=len(resolved_ids),
        max_iterations=cap,
        session_id=session_id,
        run_selector=run_selector,
    )

    # ------------------------------------------------------------------ #
    # Build the initial AgentState and invoke the graph.
    # ------------------------------------------------------------------ #
    initial: AgentState = {
        "run_id": run_id,
        "dataset_ids": list(resolved_ids),
        "session_id": session_id,
        "question": question,
        "conversation_history": conversation_history,
        "action_history": [],
        "iteration_count": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "charts": [],
        "status": "running",
        "max_iterations": cap,
        "error": None,
        "selector_reasoning": selector_reasoning,
    }

    config = {"recursion_limit": cap * 3 + 10}
    final: dict[str, Any] = agentic_ai.invoke(initial, config=config)

    status = final.get("status", "completed")
    answer = final.get("answer")
    action_history = final.get("action_history") or []
    iteration_count = final.get("iteration_count", 0)
    tokens_input = final.get("tokens_input", 0)
    tokens_output = final.get("tokens_output", 0)
    error_message = final.get("error_message") or final.get("error")
    selector_reasoning = final.get("selector_reasoning", selector_reasoning)
    charts = final.get("charts") or []
    dataset_context = final.get("dataset_context") or ""
    is_best_effort = status == "completed" and error_message in (
        "max_iterations",
        "consecutive_errors",
    )

    # ------------------------------------------------------------------ #
    # Follow-up suggestions (graph-adjacent; add its tokens to the total).
    # ------------------------------------------------------------------ #
    suggested_questions: list[str] = []
    if status == "completed" and answer:
        suggested_questions, s_in, s_out = generate_suggestions(question, answer)
        tokens_input += s_in
        tokens_output += s_out

    # C29 prompt breakdown (approximate).
    prompt_breakdown = _build_prompt_breakdown(
        question=question,
        conversation_history=conversation_history,
        dataset_context=dataset_context,
        memory_block=_safe_memory_block(),
        action_history=action_history,
        tokens_input=tokens_input,
    )

    # ------------------------------------------------------------------ #
    # Persist the result to the query_runs row.
    # ------------------------------------------------------------------ #
    with create_db_session() as session:
        row = session.get(QueryRunRow, run_id)
        if row is not None:
            row.status = status
            row.answer = answer
            row.action_history = action_history
            row.iteration_count = iteration_count
            row.tokens_input = tokens_input
            row.tokens_output = tokens_output
            row.error_message = error_message
            row.selector_reasoning = selector_reasoning
            row.prompt_breakdown = prompt_breakdown

    logger.info(
        "run_done",
        run_id=run_id,
        status=status,
        iterations=iteration_count,
        is_best_effort=is_best_effort,
        suggestions=len(suggested_questions),
    )

    return {
        "type": "answer",
        "run_id": run_id,
        "session_id": session_id,
        "status": status,
        "answer": answer,
        "iteration_count": iteration_count,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "action_history": action_history,
        "charts": charts,
        "dataset_ids": list(resolved_ids),
        "is_best_effort": is_best_effort,
        "selector_reasoning": selector_reasoning,
        "suggested_questions": suggested_questions,
        "prompt_breakdown": prompt_breakdown,
    }
