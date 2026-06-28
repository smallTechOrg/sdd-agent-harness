"""Question routes: ask (SSE step stream), fetch one question, daily cost.

``POST /datasets/{id}/ask`` returns a ``text/event-stream``. It consumes
``graph.runner.run_agent_stream(dataset_id, question)`` — a generator that yields
step events at each node boundary and a final answer (or error) event — and maps
each to an SSE frame per spec/api.md:

    event: step    data: {"step","index","elapsed_ms"}
    event: answer  data: {question_id, answer_text, chart_spec, summary_table,
                          code, usage{...}, daily_total_usd, status:"completed"}
    event: error   data: {question_id, message, code_attempted, status:"stuck"}

The runner persists the ``questions`` row before the terminal event. The handler
wraps the runner so a missing key / provider error surfaces as an ``event: error``
frame, never an unhandled 500 mid-stream.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from api._common import api_error, ok
from api.schemas import AskRequest, CostTodayResponse, QuestionResponse, Usage
from db.models import Dataset, Question
from db.session import create_db_session, get_session

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _today_cost(session: Session) -> tuple[float, int]:
    """``(total_usd, question_count)`` over questions created today (server-local)."""
    today = date.today().isoformat()
    stmt = select(
        func.coalesce(func.sum(Question.cost_usd), 0.0),
        func.count(Question.id),
    ).where(func.date(Question.created_at) == today)
    total, count = session.execute(stmt).one()
    return float(total or 0.0), int(count or 0)


def _json_or_none(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _question_payload(row: Question, daily_total: float) -> dict:
    return {
        "question_id": row.id,
        "answer_text": row.answer_text,
        "chart_spec": _json_or_none(row.chart_spec_json),
        "summary_table": _json_or_none(row.summary_table_json),
        "code": row.code,
        "usage": {
            "prompt_tokens": row.prompt_tokens or 0,
            "completion_tokens": row.completion_tokens or 0,
            "cost_usd": row.cost_usd or 0.0,
        },
        "daily_total_usd": round(daily_total, 6),
        "status": row.status,
    }


def _classify_event(event: dict) -> str:
    """Normalise a runner event to one of: ``step`` | ``answer`` | ``error``."""
    kind = event.get("type") or event.get("event") or event.get("kind")
    if kind in ("step", "answer", "error"):
        return kind
    if "step" in event:
        return "step"
    if event.get("status") in ("stuck", "failed") or "message" in event:
        return "error"
    return "answer"


# --------------------------------------------------------------------------- #
# POST /datasets/{id}/ask  (SSE)
# --------------------------------------------------------------------------- #
@router.post("/datasets/{dataset_id}/ask")
def ask_question(
    dataset_id: str,
    req: AskRequest,
    session: Session = Depends(get_session),
):
    # Validate the dataset exists BEFORE streaming so an unknown id is a clean 404.
    if session.get(Dataset, dataset_id) is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)

    question = req.question

    def _event_stream():
        from graph.runner import run_agent_stream

        question_id: str | None = None
        terminal_seen = False
        try:
            for raw in run_agent_stream(dataset_id, question):
                event = dict(raw) if isinstance(raw, dict) else {"answer": raw}
                if event.get("question_id"):
                    question_id = event["question_id"]
                kind = _classify_event(event)

                if kind == "step":
                    yield ServerSentEvent(
                        event="step",
                        data=json.dumps(
                            {
                                "step": event.get("step"),
                                "index": event.get("index"),
                                "elapsed_ms": event.get("elapsed_ms"),
                            }
                        ),
                    )
                    continue

                # answer or error → finalise from the persisted row for a uniform shape
                terminal_seen = True
                qid = question_id or event.get("question_id")
                with create_db_session() as s:
                    total, _ = _today_cost(s)
                    row = s.get(Question, qid) if qid else None
                    if row is not None and kind == "answer":
                        yield ServerSentEvent(
                            event="answer",
                            data=json.dumps(_question_payload(row, total)),
                        )
                    elif kind == "error":
                        yield ServerSentEvent(
                            event="error",
                            data=json.dumps(
                                {
                                    "question_id": qid,
                                    "message": event.get("message")
                                    or event.get("error")
                                    or (row.error_message if row else None)
                                    or "The agent could not answer this question.",
                                    "code_attempted": event.get("code_attempted")
                                    or event.get("code")
                                    or (row.code if row else None),
                                    "status": "stuck",
                                }
                            ),
                        )
                    else:
                        # answer requested but no persisted row — fall back to event payload
                        payload = dict(event)
                        payload.setdefault("question_id", qid)
                        payload.setdefault("daily_total_usd", round(total, 6))
                        payload.setdefault("status", "completed")
                        payload.setdefault("usage", {})
                        yield ServerSentEvent(event="answer", data=json.dumps(payload))
        except Exception as exc:
            # Any provider/runner failure mid-stream surfaces as a clean error frame.
            yield ServerSentEvent(
                event="error",
                data=json.dumps(
                    {
                        "question_id": question_id,
                        "message": f"The analysis failed: {exc}",
                        "code_attempted": None,
                        "status": "stuck",
                    }
                ),
            )
            return

        if not terminal_seen:
            # The runner ended without a terminal event — emit a defensive error.
            yield ServerSentEvent(
                event="error",
                data=json.dumps(
                    {
                        "question_id": question_id,
                        "message": "The agent stopped without producing an answer.",
                        "code_attempted": None,
                        "status": "stuck",
                    }
                ),
            )

    return EventSourceResponse(_event_stream())


# --------------------------------------------------------------------------- #
# GET /questions/{id}
# --------------------------------------------------------------------------- #
@router.get("/questions/{question_id}")
def get_question(question_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(Question, question_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Question {question_id} not found", 404)

    created = row.created_at
    return ok(
        QuestionResponse(
            id=row.id,
            dataset_id=row.dataset_id,
            question=row.question,
            code=row.code,
            answer_text=row.answer_text,
            chart_spec=_json_or_none(row.chart_spec_json),
            summary_table=_json_or_none(row.summary_table_json),
            usage=Usage(
                prompt_tokens=row.prompt_tokens or 0,
                completion_tokens=row.completion_tokens or 0,
                cost_usd=row.cost_usd or 0.0,
            ),
            status=row.status,
            created_at=created.isoformat() if isinstance(created, datetime) else None,
        ).model_dump()
    )


# --------------------------------------------------------------------------- #
# GET /cost/today
# --------------------------------------------------------------------------- #
@router.get("/cost/today")
def cost_today(session: Session = Depends(get_session)) -> dict:
    total, count = _today_cost(session)
    return ok(
        CostTodayResponse(
            date=date.today().isoformat(),
            total_usd=round(total, 6),
            question_count=count,
        ).model_dump()
    )
