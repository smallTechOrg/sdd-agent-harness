from __future__ import annotations

import json

import structlog

from data_analysis_agent.graph.state import AgentState

log = structlog.get_logger()


def strip_json_fences(text: str) -> str:
    """Strip a leading ```-fence (and optional language tag) from an LLM reply."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[1:end]).strip()


def parse_tool_call(raw: str) -> tuple[dict | None, Exception | None]:
    """Parse a raw LLM reply into a ``{tool, arguments}`` dict.

    Args:
        raw: The fence-stripped LLM response expected to be a JSON tool call.

    Returns:
        ``(call, None)`` on success, or ``(None, exc)`` if it is not a valid call.
    """
    try:
        call = json.loads(raw)
        return {"tool": call["tool"], "arguments": call.get("arguments", {})}, None
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, exc


def observation(tool: str, arguments: dict, result: str, is_error: bool) -> dict:
    """Construct a single ``action_history`` entry."""
    return {"tool": tool, "arguments": arguments, "result": result, "is_error": is_error}


def invalid_call_entry(exc: Exception | None) -> dict:
    """Build the recoverable observation shown when the reply was not a tool call."""
    return observation(
        "(invalid)", {},
        f"Your response could not be parsed as a tool call ({exc}). "
        f'Respond with EITHER a single JSON object '
        f'{{"tool": "<tool_name>", "arguments": {{"query": "SELECT ..."}}}} '
        f"(no prose, no markdown) OR a line starting with 'FINAL ANSWER:'.",
        True,
    )


def loop_back(state: AgentState, entry: dict, max_iterations: int) -> AgentState:
    """Append an observation, advance the iteration counter, and continue the loop.

    Recoverable errors are fed back to ``plan_action`` for self-correction; the loop
    only gives up (setting ``state['error']``) once ``max_iterations`` is hit. Pool
    teardown is handled by ``finalize``/``handle_error``, not here.

    Args:
        state: The current agent state.
        entry: The observation to append to ``action_history``.
        max_iterations: The configured ceiling on ReAct iterations.

    Returns:
        The updated state, with ``error`` set if the iteration cap was reached.
    """
    run_id = state["run_id"]
    history = [*state.get("action_history", []), entry]
    iteration_count = state.get("iteration_count", 0) + 1
    log.info("execute_action.done", run_id=run_id, tool=entry.get("tool"),
             iteration=iteration_count, is_error=entry.get("is_error", False))
    new_state = {**state, "action_history": history, "iteration_count": iteration_count}
    if iteration_count >= max_iterations:
        return {**new_state, "error": f"Max iterations ({max_iterations}) reached without a final answer"}
    return new_state
