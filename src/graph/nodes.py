"""The DataChat plan-execute nodes (see ``spec/agent.md`` -> "Nodes / Steps").

Pipeline: profile_context -> plan -> generate_code -> execute_local -> synthesize
-> finalize, with handle_error on any fatal failure and a single self-correction
retry on a code-execution failure.

Hard rules enforced here:
- LLM nodes call Gemini ONLY through ``LLMClient`` — never the SDK directly.
- The full dataframe is loaded ONLY in ``node_execute_local`` from ``file_path``;
  it is never serialized into a prompt. ``build_llm_context`` (graph/context.py)
  is the single path that assembles LLM input.
- LLM nodes wrap the call in try/except and set ``state["error"]`` on failure so
  the conditional edge routes to ``handle_error``. ``execute_local`` sets
  ``exec_error`` (not ``error``) so the self-correction edge can fire.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import structlog

from execution.profile import load_csv
from execution.sandbox import execute_pandas
from graph.context import build_llm_context
from graph.state import AgentState
from llm.client import LLMClient
from llm.cost import cost_from_settings

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Defaults matching spec/.env.example; read from settings defensively (other
# slices own the settings module and may extend it later).
_DEFAULT_EXEC_TIMEOUT_S = 30


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _setting(name: str, default: int) -> int:
    try:
        from config.settings import get_settings

        value = getattr(get_settings(), name, None)
        return default if value is None else int(value)
    except Exception:
        return default


def _emit(state: AgentState, event: str, data: dict[str, Any]) -> None:
    """Push an event to the runner's streaming sink, if one is attached.

    The sink is the private ``_emit`` callback the runner injects. It is a no-op
    for the blocking ``run_analysis`` path (and for unit tests) where no sink is
    set. Streaming failures never break the graph.
    """
    sink = state.get("_emit")
    if sink is None:
        return
    try:
        sink(event, data)
    except Exception:  # noqa: BLE001 — a broken client must not fail the analysis
        log.warning("emit_failed", event=event, message_id=state.get("message_id"))


_CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_code(text: str) -> str:
    """Pull the pandas code out of the model's fenced block.

    Prefers a fenced ```python block; falls back to the raw text (stripped) if
    the model omitted the fence, so a missing fence degrades to "run what it
    sent" rather than failing the whole run.
    """
    match = _CODE_FENCE.search(text or "")
    if match:
        return match.group(1).strip()
    return (text or "").strip()


# --------------------------------------------------------------------------- #
# node_profile_context
# --------------------------------------------------------------------------- #

def node_profile_context(state: AgentState) -> AgentState:
    """Assemble the bounded LLM context (schema + samples + profile + history).

    No LLM call, no full data. This is the single chokepoint that enforces the
    privacy boundary; the LLM nodes read the context it produces.
    """
    context = build_llm_context(
        profile=state.get("profile", {}) or {},
        question=state.get("question", ""),
        history=state.get("messages", []) or [],
    )
    return {**state, "_context": context}


def _get_context(state: AgentState) -> str:
    """Return the assembled context, rebuilding via the chokepoint if absent.

    Guarantees that even if a node is invoked in isolation (e.g. a test feeding a
    partial state) the LLM input still flows through ``build_llm_context``.
    """
    context = state.get("_context")
    if context:
        return context
    return build_llm_context(
        profile=state.get("profile", {}) or {},
        question=state.get("question", ""),
        history=state.get("messages", []) or [],
    )


# --------------------------------------------------------------------------- #
# node_plan
# --------------------------------------------------------------------------- #

def node_plan(state: AgentState) -> AgentState:
    """Produce the explicit numbered analysis plan (Planning #6)."""
    _emit(state, "status", {"step": "planning"})
    context = _get_context(state)
    started = time.monotonic()
    try:
        system = _load_prompt("plan.md")
        text, usage = LLMClient().call_model_with_usage(context, system=system)
        plan = (text or "").strip()
        log.info(
            "node_plan",
            message_id=state.get("message_id"),
            latency_ms=round((time.monotonic() - started) * 1000, 1),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        new_state: AgentState = {
            **state,
            "plan": plan,
            "prompt_tokens": state.get("prompt_tokens", 0) + usage.prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + usage.completion_tokens,
        }
        _emit(new_state, "plan", {"plan": plan})
        return new_state
    except Exception as exc:  # noqa: BLE001 — surface as a fatal error -> handle_error
        log.error("node_plan_failed", message_id=state.get("message_id"), error=str(exc))
        return {**state, "error": f"Planning failed: {exc}"}


# --------------------------------------------------------------------------- #
# node_generate_code
# --------------------------------------------------------------------------- #

def node_generate_code(state: AgentState) -> AgentState:
    """Write pandas code realizing the plan (LLM-Generated Code Execution #22).

    On a retry (``exec_error`` set), the prior code + the execution error are
    appended so the model can self-correct.
    """
    _emit(state, "status", {"step": "generating_code"})
    context = _get_context(state)
    plan = state.get("plan") or ""

    prompt_parts = [context, f"PLAN:\n{plan}"]
    exec_error = state.get("exec_error")
    is_retry = bool(exec_error)
    if is_retry:
        prior = state.get("generated_code") or ""
        prompt_parts.append(
            "PREVIOUS ATTEMPT (this code FAILED — fix the specific cause):\n"
            f"```python\n{prior}\n```\n\nEXECUTION ERROR:\n{exec_error}"
        )
    prompt = "\n\n".join(prompt_parts)

    # This invocation IS a self-correction retry (it was re-entered because the
    # prior code raised an exec_error). Increment the retry counter now so a
    # second execution failure routes to handle_error instead of looping. This
    # is the "increment retry_count" step of the self-correction edge.
    retry_count = state.get("retry_count", 0) + (1 if is_retry else 0)

    started = time.monotonic()
    try:
        system = _load_prompt("generate_code.md")
        text, usage = LLMClient().call_model_with_usage(prompt, system=system)
        code = _extract_code(text)
        log.info(
            "node_generate_code",
            message_id=state.get("message_id"),
            retry=state.get("retry_count", 0),
            latency_ms=round((time.monotonic() - started) * 1000, 1),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
        new_state: AgentState = {
            **state,
            "generated_code": code,
            "retry_count": retry_count,
            # Clear any stale exec_error from the prior attempt now that we have
            # fresh code; execute_local sets it again only if THIS code fails.
            "exec_error": None,
            "prompt_tokens": state.get("prompt_tokens", 0) + usage.prompt_tokens,
            "completion_tokens": state.get("completion_tokens", 0) + usage.completion_tokens,
        }
        _emit(new_state, "code", {"code": code})
        return new_state
    except Exception as exc:  # noqa: BLE001 — fatal -> handle_error
        log.error("node_generate_code_failed", message_id=state.get("message_id"), error=str(exc))
        return {**state, "error": f"Code generation failed: {exc}"}


# --------------------------------------------------------------------------- #
# node_execute_local
# --------------------------------------------------------------------------- #

def node_execute_local(state: AgentState) -> AgentState:
    """Run the generated code locally over the FULL dataframe.

    Loads the full data from ``file_path`` (the only place it is materialized)
    and runs ``execute_pandas`` in the restricted sandbox. On failure, sets
    ``exec_error`` (NOT ``error``) so the self-correction edge can retry.
    """
    _emit(state, "status", {"step": "executing"})
    code = state.get("generated_code") or ""
    file_path = state.get("file_path") or ""
    timeout_s = _setting("exec_timeout_s", _DEFAULT_EXEC_TIMEOUT_S)

    started = time.monotonic()
    try:
        df = load_csv(file_path)
    except Exception as exc:  # noqa: BLE001 — file/parse error feeds self-correction
        log.error("node_execute_local_load_failed", message_id=state.get("message_id"), error=str(exc))
        return {**state, "exec_error": f"Failed to load dataset: {exc}"}

    res = execute_pandas(code, df, timeout_s)
    latency_ms = round((time.monotonic() - started) * 1000, 1)

    if res.error is not None:
        # Transparent: keep the real traceback for self-correction / the audit.
        detail = res.error
        if res.traceback:
            detail = f"{res.error}\n\n{res.traceback}"
        log.warning(
            "node_execute_local_exec_error",
            message_id=state.get("message_id"),
            retry=state.get("retry_count", 0),
            latency_ms=latency_ms,
            error=res.error,
        )
        return {**state, "exec_error": detail}

    log.info(
        "node_execute_local",
        message_id=state.get("message_id"),
        latency_ms=latency_ms,
        has_table=res.result_table is not None,
        has_numbers=res.key_numbers is not None,
    )
    return {
        **state,
        "result_table": res.result_table,
        "key_numbers": res.key_numbers,
        "exec_error": None,
    }


# --------------------------------------------------------------------------- #
# node_synthesize
# --------------------------------------------------------------------------- #

def _format_result_for_prompt(state: AgentState) -> str:
    """Render the COMPUTED result (key numbers + table) for the synthesis prompt.

    This is computed-result data derived locally — it is the answer, not the raw
    dataset — so it is safe and intended to go to the model.
    """
    import json

    key_numbers = state.get("key_numbers")
    result_table = state.get("result_table")
    parts = []
    if key_numbers is not None:
        parts.append("KEY NUMBERS:\n" + json.dumps(key_numbers, ensure_ascii=False))
    if result_table is not None:
        # The table is already capped by the sandbox (RESULT_TABLE_ROW_CAP).
        parts.append("RESULT TABLE:\n" + json.dumps(result_table, ensure_ascii=False))
    if not parts:
        parts.append("COMPUTED RESULT: (empty)")
    return "\n\n".join(parts)


def node_synthesize(state: AgentState) -> AgentState:
    """Stream the plain-English answer over the computed result.

    Streams via ``LLMClient().stream_model``: accumulates ``answer`` by
    concatenation, pushes each token delta to the emit sink, and keeps the most
    recent non-None ``usage`` as the final cumulative tokens. Then computes
    ``cost_usd`` from the accumulated token totals. On failure sets ``error``.
    """
    _emit(state, "status", {"step": "synthesizing"})
    question = state.get("question", "")
    plan = state.get("plan") or ""
    result_block = _format_result_for_prompt(state)
    prompt = "\n\n".join(
        [f"QUESTION:\n{question}", f"PLAN:\n{plan}", result_block]
    )

    started = time.monotonic()
    try:
        system = _load_prompt("synthesize.md")
        answer_parts: list[str] = []
        final_usage = None
        for chunk in LLMClient().stream_model(prompt, system=system):
            if chunk.text:
                answer_parts.append(chunk.text)
                _emit(state, "token", {"text": chunk.text})
            if chunk.usage is not None:
                final_usage = chunk.usage

        answer = "".join(answer_parts).strip()
        prompt_tokens = state.get("prompt_tokens", 0)
        completion_tokens = state.get("completion_tokens", 0)
        if final_usage is not None:
            prompt_tokens += final_usage.prompt_tokens
            completion_tokens += final_usage.completion_tokens

        cost_usd = cost_from_settings(prompt_tokens, completion_tokens)
        log.info(
            "node_synthesize",
            message_id=state.get("message_id"),
            latency_ms=round((time.monotonic() - started) * 1000, 1),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        return {
            **state,
            "answer": answer,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost_usd,
        }
    except Exception as exc:  # noqa: BLE001 — fatal -> handle_error (result already computed)
        log.error("node_synthesize_failed", message_id=state.get("message_id"), error=str(exc))
        return {**state, "error": f"Answer synthesis failed: {exc}"}


# --------------------------------------------------------------------------- #
# node_finalize / node_handle_error
# --------------------------------------------------------------------------- #

def node_finalize(state: AgentState) -> AgentState:
    """Mark the run successful. The runner persists the full messages row."""
    return {**state, "status": "completed"}


def node_handle_error(state: AgentState) -> AgentState:
    """Terminal failure.

    Sets ``status='failed'``. The offending code and the real error
    (``error`` for an LLM/fatal failure, or the final ``exec_error`` after the
    self-correction retry is exhausted) are already in state for the runner to
    persist and stream — transparency over silent retries.
    """
    error = state.get("error") or state.get("exec_error") or "Unknown error"
    log.error(
        "node_handle_error",
        message_id=state.get("message_id"),
        dataset_id=state.get("dataset_id"),
        error=error,
    )
    return {**state, "status": "failed", "error": error}
