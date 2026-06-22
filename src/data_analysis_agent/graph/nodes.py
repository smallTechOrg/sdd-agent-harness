"""LangGraph node layer.

Each function here is a graph node that wires together the focused helper modules
(``loading``, ``planning``, ``execution``, ``persistence``). Nodes stay thin: they
orchestrate, handle errors, and return a new ``AgentState`` — they never raise.
"""
from __future__ import annotations

import structlog

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.graph.data_cache import cleanup_connection
from data_analysis_agent.graph.execution import (
    FatalActionError,
    dispatch_capability,
    invalid_call_entry,
    loop_back,
    parse_tool_call,
    strip_json_fences,
)
from data_analysis_agent.graph.loading import (
    assign_table_names,
    load_sources_into_sqlite,
    open_session_db,
)
from data_analysis_agent.graph.persistence import mark_completed, mark_failed
from data_analysis_agent.graph.planning import build_plan_prompt
from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.graph.tool_registry import load_tool_registry
from data_analysis_agent.llm.client import get_llm_client
from data_analysis_agent.llm.types import LLMResult

log = structlog.get_logger()

_FINAL_PREFIX = "FINAL ANSWER:"


def load_data(state: AgentState) -> AgentState:
    """Load the session's tools and data into a fresh in-memory SQLite database.

    Args:
        state: The initial agent state carrying the ``session_id`` and ``run_id``.

    Returns:
        State enriched with ``tools``, ``column_names``, and ``row_count``, or with
        ``error`` set if no data sources are attached or loading fails.
    """
    try:
        tools, sources = load_tool_registry(state["session_id"])
        if not sources:
            return {**state, "error": "No data sources attached to this session"}
        conn = open_session_db(state["run_id"])
        column_names, row_count = load_sources_into_sqlite(conn, sources)
        resolved_tools = assign_table_names(tools, sources)
        log.info("load_data.done", run_id=state.get("run_id"), sources=len(sources),
                 tools=len(resolved_tools), total_rows=row_count)
        return {**state, "tools": resolved_tools, "column_names": column_names,
                "row_count": row_count, "action_history": [], "iteration_count": 0}
    except Exception as exc:
        log.error("load_data.failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"Failed to load data: {exc}"}


def plan_action(state: AgentState) -> AgentState:
    """Ask the LLM for the next tool call, or detect the final answer.

    Args:
        state: The current agent state with tools, schema, and history.

    Returns:
        State with ``llm_response`` and updated usage counters; ``answer`` is set
        when the model signals ``FINAL ANSWER:``. Sets ``error`` on LLM failure.
    """
    run_id = state.get("run_id", "")
    try:
        result = get_llm_client().complete(build_plan_prompt(state))
        response = result.text.strip()
        return _apply_final_answer(_accumulate_usage(state, result, response), response, run_id)
    except Exception as exc:
        log.error("plan_action.failed", run_id=run_id, error=str(exc))
        cleanup_connection(run_id)
        return {**state, "error": f"LLM action planning failed: {exc}"}


def execute_action(state: AgentState) -> AgentState:
    """Parse and run the LLM's planned tool call, then loop back to planning.

    Recoverable problems (bad JSON, unknown capability, SQL errors) are fed back
    to ``plan_action`` for self-correction; fatal problems set ``state['error']``.
    """
    run_id = state.get("run_id", "")
    try:
        max_iterations = get_settings().max_agent_iterations
        call, parse_error = parse_tool_call(strip_json_fences(state.get("llm_response", "")))
        if call is None:
            return loop_back(state, invalid_call_entry(parse_error, run_id), max_iterations)
        entry = dispatch_capability(state, call["capability"], call["parameters"])
        return loop_back(state, entry, max_iterations)
    except FatalActionError as exc:
        cleanup_connection(run_id)
        return {**state, "error": str(exc)}
    except Exception as exc:
        log.error("execute_action.failed", run_id=run_id, error=str(exc))
        cleanup_connection(run_id)
        return {**state, "error": f"Action execution failed: {exc}"}


def finalize(state: AgentState) -> AgentState:
    """Persist the final answer and usage stats, then release the run's resources.

    Args:
        state: The agent state carrying the answer and accumulated usage.

    Returns:
        The unchanged state on success, or with ``error`` set if persistence fails.
    """
    run_id = state.get("run_id", "")
    try:
        mark_completed(state)
        cleanup_connection(run_id)
        log.info("finalize.done", run_id=run_id)
        return state
    except Exception as exc:
        log.error("finalize.failed", run_id=run_id, error=str(exc))
        return {**state, "error": f"Finalize failed: {exc}"}


def handle_error(state: AgentState) -> AgentState:
    """Persist the failure, clean up the run's resources, and terminate the graph.

    Args:
        state: The agent state whose ``error`` describes the failure.

    Returns:
        The unchanged state (the graph routes this node straight to END).
    """
    run_id = state.get("run_id", "")
    error_message = state.get("error", "Unknown error")
    try:
        mark_failed(state, error_message)
        log.error("pipeline.failed", run_id=run_id, error=error_message)
    except Exception as exc:
        log.error("handle_error.db_write_failed", error=str(exc))
    finally:
        cleanup_connection(run_id)
    return state


def _accumulate_usage(state: AgentState, result: LLMResult, response: str) -> AgentState:
    """Return state with the raw response stored and usage counters advanced."""
    return {
        **state,
        "llm_response": response,
        "input_tokens": state.get("input_tokens", 0) + result.input_tokens,
        "output_tokens": state.get("output_tokens", 0) + result.output_tokens,
        "total_tokens": state.get("total_tokens", 0) + result.total_tokens,
        "estimated_cost_usd": (state.get("estimated_cost_usd") or 0.0) + (result.estimated_cost_usd or 0.0),
        "api_request_count": state.get("api_request_count", 0) + 1,
    }


def _apply_final_answer(state: AgentState, response: str, run_id: str) -> AgentState:
    """Set ``answer`` when the response is a FINAL ANSWER, and log the outcome."""
    if response.upper().startswith(_FINAL_PREFIX):
        state = {**state, "answer": response[len(_FINAL_PREFIX):].strip()}
        log.info("plan_action.final_answer", run_id=run_id, iterations=state.get("iteration_count", 0))
    else:
        log.info("plan_action.tool_call", run_id=run_id,
                 iteration=state.get("iteration_count", 0), llm_response=response[:300])
    return state
