from __future__ import annotations

import json
import sqlite3

import structlog

from data_analysis_agent.graph.data_cache import cleanup_connection, get_connection
from data_analysis_agent.graph.state import AgentState

log = structlog.get_logger()


class FatalActionError(Exception):
    """Raised when an action fails in a way the LLM cannot fix by retrying."""


def strip_json_fences(text: str) -> str:
    """Strip a leading ```-fence (and optional language tag) from an LLM reply."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[1:end]).strip()


def parse_tool_call(raw: str) -> tuple[dict | None, Exception | None]:
    """Parse a raw LLM reply into a ``{capability, parameters}`` dict.

    Args:
        raw: The fence-stripped LLM response expected to be a JSON tool call.

    Returns:
        ``(call, None)`` on success, or ``(None, exc)`` if it is not a valid call.
    """
    try:
        call = json.loads(raw)
        return {"capability": call["capability"], "parameters": call.get("parameters", {})}, None
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, exc


def dispatch_capability(state: AgentState, capability: str, parameters: dict) -> dict:
    """Run a capability against its tool and return an observation entry.

    Unknown capabilities and unsupported tool types yield recoverable error
    entries; a missing in-memory connection raises :class:`FatalActionError`.
    """
    run_id = state["run_id"]
    tools = state.get("tools", [])
    tool_type = _find_tool_type(tools, capability)
    if tool_type is None:
        return _unknown_capability_entry(capability, parameters, tools, run_id)
    if tool_type == "csv_query" and capability == "run_query":
        return _run_csv_query_entry(state["run_id"], capability, parameters)
    return _observation(
        capability, parameters,
        f"No executor available for tool type '{tool_type}'. Use 'run_query'.", True,
    )


def loop_back(state: AgentState, entry: dict, max_iterations: int) -> AgentState:
    """Append an observation, advance the iteration counter, and continue the loop.

    Recoverable errors are fed back to ``plan_action`` for self-correction; the
    loop only gives up (setting ``state['error']``) once ``max_iterations`` is hit.

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
    log.info("execute_action.done", run_id=run_id, capability=entry.get("capability"),
             iteration=iteration_count, is_error=entry.get("is_error", False))
    new_state = {**state, "action_history": history, "iteration_count": iteration_count}
    if iteration_count >= max_iterations:
        cleanup_connection(run_id)
        return {**new_state, "error": f"Max iterations ({max_iterations}) reached without a final answer"}
    return new_state


def invalid_call_entry(exc: Exception | None, run_id: str) -> dict:
    """Build the recoverable observation shown when the reply was not a tool call."""
    log.warning("execute_action.bad_json", run_id=run_id, error=str(exc))
    return _observation(
        "(invalid)", {},
        f"Your response could not be parsed as a tool call ({exc}). "
        f"Respond with EITHER a single JSON object "
        f'{{"capability": "run_query", "parameters": {{"query": "SELECT ..."}}}} '
        f"(no prose, no markdown) OR a line starting with 'FINAL ANSWER:'.",
        True,
    )


def _run_csv_query_entry(run_id: str, capability: str, parameters: dict) -> dict:
    """Execute a SQL SELECT for the run and wrap the outcome as an observation."""
    conn = get_connection(run_id)
    if conn is None:
        raise FatalActionError("In-memory DB not found — load_data must run before execute_action")
    sql = parameters.get("query", "")
    log.debug("execute_action.sql", run_id=run_id, sql=sql)
    result_str, is_error = execute_csv_query(conn, sql)
    if is_error:
        log.warning("execute_action.sql_error", run_id=run_id, sql=sql, error=result_str)
    return _observation(capability, parameters, result_str, is_error)


def execute_csv_query(conn: sqlite3.Connection, sql: str) -> tuple[str, bool]:
    """Run a read-only SQL SELECT and return ``(csv_text_or_error, is_error)``.

    Rejects any non-SELECT statement as a recoverable error and never executes it.

    Args:
        conn: The in-memory SQLite connection holding the session's tables.
        sql: The SQL statement proposed by the LLM.

    Returns:
        ``(result_csv, False)`` on success or ``(error_message, True)`` on failure.
    """
    if not sql.upper().lstrip().startswith("SELECT"):
        return f"Only SELECT statements are allowed. Got: {sql[:80]}", True
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchmany(200)
        headers = [d[0] for d in cursor.description] if cursor.description else []
        lines = [",".join(headers)]
        lines += [",".join("" if v is None else str(v) for v in row) for row in rows]
        return "\n".join(lines), False
    except sqlite3.Error as exc:
        return str(exc), True


def _unknown_capability_entry(capability: str, parameters: dict, tools: list[dict], run_id: str) -> dict:
    """Build the recoverable observation listing valid capabilities for the LLM."""
    log.warning("execute_action.unknown_capability", run_id=run_id, capability=capability)
    valid = ", ".join(_available_capabilities(tools)) or "(none)"
    return _observation(
        capability, parameters,
        f"Unknown capability '{capability}'. Note: 'capability' must be one of "
        f"the capability names, not a tool name. Valid capabilities: {valid}.",
        True,
    )


def _find_tool_type(tools: list[dict], capability: str) -> str | None:
    """Return the type of the first tool exposing ``capability``, or ``None``."""
    for tool in tools:
        if any(cap["name"] == capability for cap in tool.get("capabilities", [])):
            return tool["type"]
    return None


def _available_capabilities(tools: list[dict]) -> list[str]:
    """Return every capability name across all loaded tools."""
    return [cap["name"] for tool in tools for cap in tool.get("capabilities", [])]


def _observation(capability: str, parameters: dict, result: str, is_error: bool) -> dict:
    """Construct a single ``action_history`` entry."""
    return {"capability": capability, "parameters": parameters, "result": result, "is_error": is_error}
