"""Runner + streaming for the Pandora analysis graph (see spec/agent.md).

``run_agent_stream`` is a generator. It:
  1. loads the dataset's ``profile`` + ``parquet_path`` from the ``datasets`` row,
  2. creates a ``questions`` row (status pending),
  3. streams the compiled graph, yielding a step event per node boundary
     (mapped to the SSE step names from architecture.md),
  4. persists final code/result/usage/status,
  5. yields a final ``answer`` event (or ``error`` event on failure).

Event shapes yielded (the API route maps these to SSE):
  step:   {"type": "step",   "step": <name>, "index": <int>, "elapsed_ms": <int>}
  answer: {"type": "answer", "question_id", "status", "answer_text",
           "code", "chart_spec", "summary_table", "usage", "model"}
  error:  {"type": "error",  "question_id", "status", "error", "code", "usage", "model"}

DB sessions are kept SHORT and values are read out before each session closes
(avoids DetachedInstanceError).
"""

import json
import time
from collections.abc import Iterator

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session
from db.models import Dataset, Question
from config.settings import get_settings
from observability.events import log_question_event, log_step_event

# Node name -> SSE step name (architecture.md "Streaming Step Updates").
_STEP_NAMES = {
    "generate_code": "generating_code",
    "execute_code": "running_code",
    "summarise": "summarising",
    # validate_code / handle_error / finalize are internal — not surfaced as steps.
}


def _model_name() -> str:
    s = get_settings()
    if s.llm_model:
        return s.llm_model
    # Default per spec/architecture.md.
    return "gemini-2.5-flash"


def _load_dataset(dataset_id: str) -> tuple[dict, str]:
    """Read profile + parquet_path out of the datasets row (then close session)."""
    with create_db_session() as session:
        ds = session.get(Dataset, dataset_id)
        if ds is None:
            raise ValueError(f"Dataset {dataset_id!r} not found.")
        profile = json.loads(ds.profile_json) if ds.profile_json else {}
        parquet_path = ds.parquet_path or ""
    if not parquet_path:
        raise ValueError(f"Dataset {dataset_id!r} has no analysis data on disk.")
    return profile, parquet_path


def _create_question(dataset_id: str, question: str, model: str) -> str:
    with create_db_session() as session:
        row = Question(
            dataset_id=dataset_id,
            question=question,
            status="pending",
            model=model,
        )
        session.add(row)
        session.flush()
        qid = row.id
    return qid


def _persist_final(question_id: str, final: AgentState) -> None:
    usage = final.get("usage") or {}
    chart_spec = final.get("chart_spec")
    summary_table = final.get("summary_table")
    status = final.get("status") or ("stuck" if final.get("error") else "completed")

    with create_db_session() as session:
        row = session.get(Question, question_id)
        if row is None:
            return
        row.code = final.get("code")
        row.answer_text = final.get("answer_text")
        row.chart_spec_json = json.dumps(chart_spec) if chart_spec is not None else None
        row.summary_table_json = json.dumps(summary_table) if summary_table is not None else None
        row.prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        row.completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        row.cost_usd = float(usage.get("cost_usd", 0.0) or 0.0)
        row.status = status
        row.error_message = final.get("error")


def run_agent_stream(
    dataset_id: str,
    question: str,
    conversation: list | None = None,
) -> Iterator[dict]:
    """Stream step events, then a final answer/error event. See module docstring."""
    started = time.monotonic()
    model = _model_name()

    def _elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    def _emit_question_event(
        question_id: str | None,
        final: AgentState | None,
        status: str,
    ) -> None:
        """Emit exactly one structured per-question event (metadata/counts/cost only).

        ``status`` is the runner status ("completed"|"failed"|"stuck"); it is
        mapped to the observability convention ("ok" for a completed run, the
        raw status otherwise so failures log at error level). NEVER pass raw
        dataset rows or values here — only the question text, counts, and cost.
        """
        usage = (final.get("usage") if final else None) or {}
        log_question_event(
            dataset_id=dataset_id,
            question_id=question_id or "",
            status="ok" if status == "completed" else status,
            attempts=int((final.get("attempts") if final else 0) or 0),
            exec_ms=_elapsed_ms(),
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            cost_usd=float(usage.get("cost_usd", 0.0) or 0.0),
            model=model,
            node_sequence=list(node_sequence),
            error=(final.get("error") if final else None),
        )

    node_sequence: list[str] = []

    # Load dataset + create the question row up front; a failure here is terminal.
    try:
        profile, parquet_path = _load_dataset(dataset_id)
    except Exception as exc:
        yield {
            "type": "error",
            "question_id": None,
            "status": "failed",
            "error": str(exc),
            "code": None,
            "usage": {},
            "model": model,
        }
        _emit_question_event(None, {"error": str(exc)}, "failed")
        return

    question_id = _create_question(dataset_id, question, model)

    initial: AgentState = {
        "run_id": question_id,
        "dataset_id": dataset_id,
        "dataset_path": parquet_path,
        "profile": profile,
        "question": question,
        "messages": conversation or [],
        "attempts": 0,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
    }

    final_state: AgentState = dict(initial)
    index = 0
    seen_generate = False

    try:
        for update in agentic_ai.stream(initial, stream_mode="updates"):
            # `updates` mode yields {node_name: state_delta} per node boundary.
            for node_name, delta in update.items():
                if isinstance(delta, dict):
                    final_state.update(delta)

                node_sequence.append(node_name)

                if node_name not in _STEP_NAMES:
                    continue

                step = _STEP_NAMES[node_name]
                # A second visit to generate_code means we are retrying.
                if node_name == "generate_code":
                    if seen_generate:
                        step = "retrying"
                    seen_generate = True

                index += 1
                elapsed = _elapsed_ms()
                # Optional per-step debug event (silent unless AGENT_LOG_LEVEL=DEBUG).
                log_step_event(
                    question_id=question_id,
                    step=step,
                    index=index,
                    elapsed_ms=elapsed,
                )
                yield {
                    "type": "step",
                    "step": step,
                    "index": index,
                    "elapsed_ms": elapsed,
                }
    except Exception as exc:
        # Graph itself blew up — persist what we have, emit a terminal error.
        final_state["status"] = "failed"
        final_state["error"] = f"Analysis failed: {exc}"
        _persist_final(question_id, final_state)
        _emit_question_event(question_id, final_state, "failed")
        yield {
            "type": "error",
            "question_id": question_id,
            "status": "failed",
            "error": final_state["error"],
            "code": final_state.get("code"),
            "usage": final_state.get("usage") or {},
            "model": model,
        }
        return

    _persist_final(question_id, final_state)

    status = final_state.get("status") or ("stuck" if final_state.get("error") else "completed")
    usage = final_state.get("usage") or {}

    _emit_question_event(question_id, final_state, status)

    if status == "completed":
        yield {
            "type": "answer",
            "question_id": question_id,
            "status": status,
            "answer_text": final_state.get("answer_text"),
            "code": final_state.get("code"),
            "chart_spec": final_state.get("chart_spec"),
            "summary_table": final_state.get("summary_table"),
            "usage": usage,
            "model": model,
        }
    else:
        yield {
            "type": "error",
            "question_id": question_id,
            "status": status,
            "error": final_state.get("error") or "The analysis could not be completed.",
            "code": final_state.get("code"),
            "usage": usage,
            "model": model,
        }
