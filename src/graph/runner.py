"""Runner — the single entry the API calls for one chat turn.

The runner owns all DB row reads/writes that bracket the graph: it creates the
conversation, loads the dataset (schema + file path), loads recent history,
persists the user Message, creates the RunRow, builds the initial AgentState and
invokes the compiled graph. The graph's ``finalize`` / ``handle_error`` nodes
persist the assistant Message. The runner then returns the ``/chat`` data shape.
"""
from __future__ import annotations

import json

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session
from db.models import Dataset, Conversation, Message, RunRow
from data.storage import resolve_path

# How many recent turns to pass into plan_aggregation for follow-up context.
DEFAULT_HISTORY_TURNS = 6


class DatasetNotFound(Exception):
    """Raised when the requested dataset_id has no row."""


def _load_recent_history(session, conversation_id: str, limit: int) -> list:
    """Return the last ``limit`` messages (chronological) as [{role, content}]."""
    rows = (
        session.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    return [{"role": m.role, "content": m.content} for m in rows]


def run_chat_turn(
    dataset_id: str,
    question: str,
    conversation_id: str | None,
    *,
    history_turns: int = DEFAULT_HISTORY_TURNS,
) -> dict:
    """Run one DataChat turn end-to-end.

    Returns the ``/chat`` data shape:
        {"conversation_id": str, "answer": str, "chart": dict | None}

    Raises DatasetNotFound if ``dataset_id`` does not exist.
    """
    with create_db_session() as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise DatasetNotFound(dataset_id)

        schema = json.loads(dataset.schema_json)
        file_path = resolve_path(dataset.id, dataset.file_type)

        # Create the conversation on first turn, or load history for a follow-up.
        if conversation_id is None:
            conversation = Conversation(dataset_id=dataset_id)
            session.add(conversation)
            session.flush()
            conversation_id = conversation.id
            history: list = []
        else:
            history = _load_recent_history(session, conversation_id, history_turns)

        # Persist the user's question.
        session.add(
            Message(conversation_id=conversation_id, role="user", content=question)
        )

        # Create the RunRow for this turn (internal execution record).
        run = RunRow(input_text=question, status="running")
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "dataset_id": dataset_id,
        "file_path": file_path,
        "schema": schema,
        "question": question,
        "history": history,
        "error": None,
    }

    # finalize / handle_error persist the assistant Message + run status.
    final = agentic_ai.invoke(initial)

    return {
        "conversation_id": conversation_id,
        "answer": final.get("answer"),
        "chart": final.get("chart"),
    }
