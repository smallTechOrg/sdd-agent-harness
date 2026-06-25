"""LangGraph node layer (async).

The per-query loop is ``plan_action → execute_action → finalize / handle_error``. There is no
``load_data`` node — the session's MCP pool is acquired by ``run_pipeline`` before the graph runs
(once per session, reused across queries). Nodes read tools/schema from the ``SessionPoolManager``
by ``session_id`` and never close the pool (the manager owns its lifecycle).

LangGraph runs each node in its own asyncio task, so MCP ``ClientSession``s stay transient
(opened/closed inside ``manager.call_tool``). See spec/product/07-agent-graph.md.
"""
from __future__ import annotations

import structlog

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.graph.execution import (
    invalid_call_entry,
    loop_back,
    observation,
    parse_tool_call,
    strip_json_fences,
)
from data_analysis_agent.graph.persistence import mark_completed, mark_failed
from data_analysis_agent.graph.planning import build_plan_prompt
from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.llm.client import get_llm_client
from data_analysis_agent.llm.types import LLMResult
from data_analysis_agent.tools.mcp.pool import get_manager

log = structlog.get_logger()

_FINAL_PREFIX = "FINAL ANSWER:"


async def plan_action(state: AgentState) -> AgentState:
    """Ask the LLM for the next tool call, or detect the final answer (entry node).

    Reads the session's tools + schema from the pool manager; the pool was acquired before
    the graph ran. Returns state with ``llm_response`` (or ``answer`` on FINAL ANSWER) and
    advanced usage counters; sets ``error`` on LLM failure.
    """
    run_id = state.get("run_id", "")
    session_id = state.get("session_id", "")
    try:
        tools, column_names = get_manager().snapshot(session_id)
        result = get_llm_client().complete(build_plan_prompt(state, tools, column_names))
        response = result.text.strip()
        return _apply_final_answer(_accumulate_usage(state, result, response), response, run_id)
    except Exception as exc:
        log.error("plan_action.failed", run_id=run_id, error=str(exc))
        return {**state, "error": f"LLM action planning failed: {exc}"}


async def execute_action(state: AgentState) -> AgentState:
    """Parse and run the LLM's planned MCP tool call, then loop back to planning.

    Recoverable problems (bad JSON, unknown tool, SQL errors) are fed back to ``plan_action``;
    fatal problems set ``state['error']``.
    """
    run_id = state.get("run_id", "")
    session_id = state.get("session_id", "")
    try:
        max_iterations = get_settings().max_agent_iterations
        call, parse_error = parse_tool_call(strip_json_fences(state.get("llm_response", "")))
        if call is None:
            log.warning("execute_action.bad_json", run_id=run_id, error=str(parse_error))
            return loop_back(state, invalid_call_entry(parse_error), max_iterations)
        result_text, is_error = await get_manager().call_tool(session_id, call["tool"], call["arguments"])
        entry = observation(call["tool"], call["arguments"], result_text, is_error)
        return loop_back(state, entry, max_iterations)
    except Exception as exc:
        log.error("execute_action.failed", run_id=run_id, error=str(exc))
        return {**state, "error": f"Action execution failed: {exc}"}


async def finalize(state: AgentState) -> AgentState:
    """Persist the answer/usage and append this turn to durable memory.

    ``conversation`` is a plain "last-value" channel, so we return the FULL updated list
    (restored history + this turn); the overwrite is idempotent if the checkpointer replays
    it on resume. Does not touch the pool.
    """
    run_id = state.get("run_id", "")
    try:
        mark_completed(state)
        turn = {"question": state.get("question", ""), "answer": state.get("answer", "")}
        conversation = [*state.get("conversation", []), turn]
        log.info("finalize.done", run_id=run_id)
        return {"conversation": conversation}
    except Exception as exc:
        log.error("finalize.failed", run_id=run_id, error=str(exc))
        return {"error": f"Finalize failed: {exc}"}


async def handle_error(state: AgentState) -> AgentState:
    """Persist the failure and terminate the graph. Does not touch the session pool."""
    run_id = state.get("run_id", "")
    error_message = state.get("error", "Unknown error")
    try:
        mark_failed(state, error_message)
        log.error("pipeline.failed", run_id=run_id, error=error_message)
    except Exception as exc:
        log.error("handle_error.db_write_failed", error=str(exc))
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
