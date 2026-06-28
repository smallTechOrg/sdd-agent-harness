"""Runner for the DataChat plan-execute agent — two entry points.

``run_analysis(dataset_id, question)`` — BLOCKING. Creates the ``running``
messages row, invokes the graph to completion, persists the terminal row, and
returns the ``message_id``. Used by the integration tests and any non-streaming
caller.

``stream_analysis(dataset_id, question)`` — a SYNC GENERATOR yielding typed SSE
events (see the docstring on the function for the exact event shape). The
api-routes slice wraps it in ``sse_starlette.EventSourceResponse``. It loads the
dataset (profile + file_path) from the DB by id, loads the trimmed history,
creates the ``running`` row up front (so ``message_id`` is known before
streaming), runs the graph while streaming ``synthesize`` tokens live, then
persists the terminal row and emits ``done`` / ``error``.

Both share the same graph invocation and the same persistence, so a streamed run
and a blocking run produce identical messages rows.
"""

from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Iterator

import structlog

from db.models import DatasetRow, MessageRow
from db.session import create_db_session
from graph.agent import agentic_ai
from graph.state import AgentState

log = structlog.get_logger(__name__)

# Default history window (last N turns) — matches spec/.env.example
# AGENT_HISTORY_TURNS. Read defensively from settings.
_DEFAULT_HISTORY_TURNS = 6

# Sentinel pushed onto the event queue when the graph thread finishes.
_DONE = object()


class DatasetNotFoundError(LookupError):
    """Raised by the runner when ``dataset_id`` does not exist.

    The api-routes slice maps this to a 404 ``NOT_FOUND`` BEFORE the stream
    starts (per spec/api.md pre-stream error cases).
    """


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _history_turns() -> int:
    try:
        from config.settings import get_settings

        value = getattr(get_settings(), "history_turns", None)
        return _DEFAULT_HISTORY_TURNS if value is None else int(value)
    except Exception:
        return _DEFAULT_HISTORY_TURNS


def _load_dataset(session, dataset_id: str) -> tuple[dict, str]:
    """Return (profile_dict, file_path) for ``dataset_id`` or raise NotFound."""
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise DatasetNotFoundError(dataset_id)
    try:
        profile = json.loads(row.profile_json) if row.profile_json else {}
    except (TypeError, json.JSONDecodeError):
        profile = {}
    return profile, row.file_path


def _load_history(session, dataset_id: str) -> list[dict[str, str]]:
    """Build the trimmed conversation history for the prompt.

    Only the prior question + completed answer TEXT is included (never any
    data), ordered oldest-first, trimmed to the last ``AGENT_HISTORY_TURNS``
    completed turns. Each completed message contributes a user turn (question)
    and an assistant turn (answer).
    """
    rows = (
        session.query(MessageRow)
        .filter(MessageRow.dataset_id == dataset_id)
        .filter(MessageRow.status == "completed")
        .order_by(MessageRow.created_at.asc())
        .all()
    )
    turns: list[dict[str, str]] = []
    for row in rows:
        if row.question:
            turns.append({"role": "user", "content": row.question})
        if row.answer:
            turns.append({"role": "assistant", "content": row.answer})
    cap = _history_turns() * 2  # a turn = one user + one assistant message
    return turns[-cap:] if cap > 0 else []


def _create_running_message(session, dataset_id: str, question: str) -> str:
    """Insert a ``running`` messages row and return its id (committed)."""
    row = MessageRow(dataset_id=dataset_id, question=question, status="running")
    session.add(row)
    session.flush()
    return row.id


def _build_initial_state(
    message_id: str,
    dataset_id: str,
    question: str,
    profile: dict,
    file_path: str,
    history: list[dict[str, str]],
    emit=None,
) -> AgentState:
    state: AgentState = {
        "message_id": message_id,
        "dataset_id": dataset_id,
        "question": question,
        "profile": profile,
        "file_path": file_path,
        "messages": history,
        "retry_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "error": None,
        "exec_error": None,
    }
    if emit is not None:
        state["_emit"] = emit
    return state


def _persist_terminal(message_id: str, final: dict[str, Any]) -> None:
    """Write the terminal messages row from the graph's final state.

    Records plan, code, answer, key_numbers/result_table (as JSON text), token
    totals, cost, status, error, and completed_at. On a failed run the offending
    ``generated_code`` and the real ``error`` are persisted — transparency over
    silent retries.
    """
    status = final.get("status") or ("failed" if final.get("error") else "completed")
    error = final.get("error") or final.get("exec_error")
    key_numbers = final.get("key_numbers")
    result_table = final.get("result_table")

    with create_db_session() as session:
        row = session.get(MessageRow, message_id)
        if row is None:  # pragma: no cover — created up front, should always exist
            log.error("persist_terminal_missing_row", message_id=message_id)
            return
        row.plan = final.get("plan")
        row.generated_code = final.get("generated_code")
        row.answer = final.get("answer")
        row.key_numbers_json = json.dumps(key_numbers) if key_numbers is not None else None
        row.result_table_json = json.dumps(result_table) if result_table is not None else None
        row.prompt_tokens = int(final.get("prompt_tokens", 0) or 0)
        row.completion_tokens = int(final.get("completion_tokens", 0) or 0)
        row.cost_usd = float(final.get("cost_usd", 0.0) or 0.0)
        row.status = status
        row.error = error
        row.completed_at = _now()


def _done_payload(message_id: str, final: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "key_numbers": final.get("key_numbers"),
        "result_table": final.get("result_table"),
        "prompt_tokens": int(final.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(final.get("completion_tokens", 0) or 0),
        "cost_usd": float(final.get("cost_usd", 0.0) or 0.0),
        "status": "completed",
    }


def _error_payload(message_id: str, final: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "error": final.get("error") or final.get("exec_error") or "Unknown error",
        "code": final.get("generated_code"),
        "status": "failed",
    }


# --------------------------------------------------------------------------- #
# Blocking entry point
# --------------------------------------------------------------------------- #

def run_analysis(
    dataset_id: str,
    question: str,
    *,
    db_session_factory=None,  # accepted for symmetry/tests; default uses create_db_session
) -> str:
    """Run one analysis to completion (blocking) and return the message_id.

    Creates the ``running`` messages row, invokes the graph, and persists the
    terminal row (completed or failed). No streaming sink is attached, so the
    synthesize tokens are simply accumulated into ``answer``.

    Raises :class:`DatasetNotFoundError` if ``dataset_id`` is unknown.
    """
    with create_db_session() as session:
        profile, file_path = _load_dataset(session, dataset_id)
        history = _load_history(session, dataset_id)
        message_id = _create_running_message(session, dataset_id, question)

    initial = _build_initial_state(
        message_id, dataset_id, question, profile, file_path, history, emit=None
    )
    log.info("run_analysis_start", message_id=message_id, dataset_id=dataset_id)
    final = dict(agentic_ai.invoke(initial))
    _persist_terminal(message_id, final)
    log.info(
        "run_analysis_done",
        message_id=message_id,
        status=final.get("status"),
        cost_usd=final.get("cost_usd"),
    )
    return message_id


# --------------------------------------------------------------------------- #
# Streaming entry point
# --------------------------------------------------------------------------- #

def stream_analysis(dataset_id: str, question: str) -> Iterator[dict[str, Any]]:
    """Run one analysis, yielding SSE-shaped events as the graph progresses.

    This is a SYNC generator. The api-routes slice wraps it in
    ``sse_starlette.EventSourceResponse``; each yielded dict maps directly to one
    SSE frame: yield ``{"event": <name>, "data": <json-serializable dict>}`` and
    the endpoint emits ``event: <name>\\n data: <json.dumps(data)>``.

    Yielded events (in order), matching spec/api.md:
      {"event": "status", "data": {"step": "planning"|"generating_code"|"executing"|"synthesizing"}}
      {"event": "plan",   "data": {"plan": "1. ...\\n2. ..."}}
      {"event": "code",   "data": {"code": "result = ..."}}
      {"event": "token",  "data": {"text": "<next chunk of the streamed answer>"}}   (repeated)
      {"event": "done",   "data": {"message_id", "key_numbers", "result_table",
                                    "prompt_tokens", "completion_tokens", "cost_usd",
                                    "status": "completed"}}
      {"event": "error",  "data": {"message_id", "error", "code", "status": "failed"}}

    Exactly one terminal event is yielded: ``done`` on success, ``error`` on
    failure. The server does NOT raise for an analysis failure — it rides the
    stream as the ``error`` event (per spec/api.md). The only pre-stream raise is
    :class:`DatasetNotFoundError` (unknown dataset_id), which the route maps to a
    404 BEFORE calling this generator.

    Mechanics: the dataset/profile/file_path and trimmed history are loaded and
    the ``running`` messages row is created up front (so ``message_id`` is known).
    The graph runs on a worker thread; node events (status/plan/code/token) are
    pushed onto a thread-safe queue via the injected ``_emit`` sink and drained
    here so synthesize tokens stream live. When the graph finishes, the terminal
    messages row is persisted and the ``done``/``error`` event is yielded.
    """
    # --- Pre-stream setup (may raise DatasetNotFoundError -> 404 by the route).
    with create_db_session() as session:
        profile, file_path = _load_dataset(session, dataset_id)
        history = _load_history(session, dataset_id)
        message_id = _create_running_message(session, dataset_id, question)

    events: "queue.Queue[Any]" = queue.Queue()

    def emit(event: str, data: dict[str, Any]) -> None:
        events.put({"event": event, "data": data})

    state = _build_initial_state(
        message_id, dataset_id, question, profile, file_path, history, emit=emit
    )

    result_holder: dict[str, Any] = {}

    def _run() -> None:
        try:
            result_holder["final"] = dict(agentic_ai.invoke(state))
        except Exception as exc:  # noqa: BLE001 — surface as a stream error, never crash
            log.error("stream_analysis_graph_error", message_id=message_id, error=str(exc))
            result_holder["final"] = {
                "status": "failed",
                "error": f"Unexpected graph error: {exc}",
            }
        finally:
            events.put(_DONE)

    log.info("stream_analysis_start", message_id=message_id, dataset_id=dataset_id)
    worker = threading.Thread(target=_run, daemon=True)
    worker.start()

    # Drain node events live until the worker signals completion.
    while True:
        item = events.get()
        if item is _DONE:
            break
        yield item

    worker.join()
    final = result_holder.get("final", {"status": "failed", "error": "No result produced."})

    # Persist the terminal row, then yield the single terminal event.
    _persist_terminal(message_id, final)
    status = final.get("status") or ("failed" if final.get("error") else "completed")
    if status == "completed":
        log.info("stream_analysis_done", message_id=message_id, status="completed")
        yield {"event": "done", "data": _done_payload(message_id, final)}
    else:
        log.info("stream_analysis_done", message_id=message_id, status="failed")
        yield {"event": "error", "data": _error_payload(message_id, final)}
