"""Chat endpoints — ask a question about a dataset; fetch a conversation thread.

`POST /chat` validates the dataset + question, then delegates the whole agent
turn to `graph.runner.run_chat_turn` (which plans → aggregates locally →
composes an answer + optional chart and persists the conversation + messages).
`GET /conversations/{id}` reads the stored thread back.
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import Conversation, Dataset, Message
from db.session import get_session
from domain.chat import ChatRequest, ChatResponse, ConversationResponse

router = APIRouter()

# Substrings that mark a runner failure as a missing-file-on-disk condition.
_MISSING_FILE_MARKERS = ("missing", "not found", "no such file")
# Substrings that mark a runner failure as an LLM/Gemini call failure.
_LLM_MARKERS = ("gemini", "llm", "language model", "api key", "quota", "rate limit")


def _classify_runner_error(exc: Exception) -> tuple[str, str, int]:
    """Map a runner exception to (code, message, status) per spec/api.md.

    - missing referenced file on disk → 400 BAD_REQUEST
    - Gemini/LLM call failure         → 502 LLM_ERROR
    - anything else                   → 500 INTERNAL
    """
    text = f"{type(exc).__name__}: {exc}".lower()

    if isinstance(exc, FileNotFoundError) or any(m in text for m in _MISSING_FILE_MARKERS):
        return "BAD_REQUEST", f"Referenced file unavailable: {exc}", 400
    if any(m in text for m in _LLM_MARKERS):
        return "LLM_ERROR", f"LLM call failed: {exc}", 502
    return "INTERNAL", f"Chat turn failed: {exc}", 500


@router.post("/chat")
def chat(req: ChatRequest, session: Session = Depends(get_session)) -> dict:
    if session.get(Dataset, req.dataset_id) is None:
        raise api_error("NOT_FOUND", f"Dataset {req.dataset_id} not found", 404)

    if not req.question or not req.question.strip():
        raise api_error("BAD_REQUEST", "Question must not be empty", 400)

    # Imported lazily: the runner is a sibling backend slice; importing here keeps
    # the router importable even while that slice is still being built.
    from graph.runner import run_chat_turn

    try:
        result = run_chat_turn(req.dataset_id, req.question, req.conversation_id)
    except Exception as exc:
        code, message, status = _classify_runner_error(exc)
        raise api_error(code, message, status)

    return ok(
        ChatResponse(
            conversation_id=result["conversation_id"],
            answer=result["answer"],
            chart=result.get("chart"),
        ).model_dump()
    )


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str, session: Session = Depends(get_session)
) -> dict:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise api_error("NOT_FOUND", f"Conversation {conversation_id} not found", 404)

    rows = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    messages = [
        {
            "role": m.role,
            "content": m.content,
            "chart": json.loads(m.chart_json) if m.chart_json else None,
        }
        for m in rows
    ]

    return ok(
        ConversationResponse(
            conversation_id=conv.id,
            dataset_id=conv.dataset_id,
            messages=messages,
        ).model_dump()
    )
