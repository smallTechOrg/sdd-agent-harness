from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_analyst.api._common import ok, api_error
from data_analyst.db.models import SessionRow, MessageRow, RunRow
from data_analyst.db.session import get_session

router = APIRouter()


class AskRequest(BaseModel):
    question: str


@router.post("/{session_id}/messages")
def ask_question(
    session_id: str,
    body: AskRequest,
    db: Session = Depends(get_session),
):
    session_row = db.get(SessionRow, session_id)
    if not session_row:
        raise api_error("SESSION_NOT_FOUND", "Session not found", status_code=404)

    if session_row.status != "ready":
        raise api_error(
            "SESSION_NOT_READY",
            f"Session is not ready (status: {session_row.status})",
            status_code=422,
        )

    user_msg = MessageRow(
        session_id=session_id,
        role="user",
        content=body.question,
    )
    db.add(user_msg)

    run = RunRow(session_id=session_id)
    db.add(run)
    db.flush()
    run_id = run.id

    session_row.last_active_at = datetime.now(timezone.utc)
    db.commit()

    from data_analyst.graph.runner import run_agent

    final_state = run_agent(
        session_id=session_id,
        run_id=run_id,
        dataset_path=session_row.file_path,
        user_question=body.question,
    )

    answer = final_state.get("final_answer") or final_state.get("error") or "No answer produced"
    action_history = final_state.get("action_history", [])

    tokens_input = final_state.get("tokens_input", 0)
    tokens_output = final_state.get("tokens_output", 0)

    assistant_msg = MessageRow(
        session_id=session_id,
        role="assistant",
        content=answer,
        reasoning_trace=json.dumps(action_history),
        iteration_count=final_state.get("iteration_count", 0),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
    )
    db.add(assistant_msg)
    db.commit()

    return ok({
        "answer": answer,
        "reasoning_trace": action_history,
        "iteration_count": final_state.get("iteration_count", 0),
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "llm_provider": __import__("data_analyst.config.settings", fromlist=["get_settings"]).get_settings().resolved_llm_provider,
    })
