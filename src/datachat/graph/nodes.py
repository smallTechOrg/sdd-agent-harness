"""Graph nodes — (state) → state. The ReAct loop's reason/act/observe + terminals.

Follows patterns/react-agent.md and 07-agent-graph.md. Recoverable action errors are
appended to action_history and loop back to plan_action; fatal errors set state["error"]
and route to handle_error. The session-scoped DuckDB engine is never released here.
"""

from __future__ import annotations

import json
from typing import Any

from datachat.config.settings import get_settings
from datachat.graph.state import AgentState
from datachat.graph.tools_schema import TOOLS
from datachat.llm.model import get_model, usage_from_response
from datachat.memory import context
from datachat.observability.events import estimate_cost_usd, get_logger, span
from datachat.prompts import load
from datachat.tools.sql_tools import (
    tool_inspect_schema,
    tool_run_sql,
    tool_suggest_chart,
)

_RESULT_PREVIEW_CHARS = 4000


def _as_text(content: Any) -> str:
    """Gemini may return content as a list of blocks (extended thinking) — flatten to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content) if content is not None else ""


def _logger(state: AgentState):
    return get_logger(
        run_id=state.get("run_id"),
        conversation_id=state.get("conversation_id"),
        dataset_id=state.get("dataset_id"),
    )


def node_assemble_context(state: AgentState) -> AgentState:
    """setup: ensure DuckDB tables are loaded; load schema/sample + recent turns."""
    from datachat.data import engine

    log = _logger(state)
    log.info("run.start", node="assemble_context", question=state.get("question"))

    if not engine.has_connection(state["dataset_id"]):
        return {**state, "error": "DATASET_NOT_LOADED: the dataset has no loaded data."}

    state.setdefault("action_history", [])
    state.setdefault("iteration_count", 0)
    state.setdefault("tokens_input", 0)
    state.setdefault("tokens_output", 0)
    return state


def node_plan_action(state: AgentState) -> AgentState:
    """reason/plan: ask Gemini for the next tool call."""
    log = _logger(state)
    messages = context.build(
        schema_summary=state["schema_summary"],
        sample_rows=state["sample_rows"],
        recent_turns=state.get("recent_turns", []),
        question=state["question"],
        action_history=state.get("action_history", []),
    )
    model = get_model().bind_tools(TOOLS)
    try:
        with span("gemini.plan_action", model=get_settings().llm_model):
            response = model.invoke(messages)
    except Exception as exc:
        log.error("run.error", node="plan_action", error=str(exc))
        return {**state, "error": f"LLM_UNAVAILABLE: {exc}"}

    tin, tout = usage_from_response(response)
    tokens_input = state.get("tokens_input", 0) + tin
    tokens_output = state.get("tokens_output", 0) + tout

    calls = getattr(response, "tool_calls", None) or []
    if calls:
        last = {"name": calls[0]["name"], "args": calls[0].get("args", {})}
    else:
        # No tool call — treat the prose as a finish answer so the loop still terminates.
        last = {"name": "finish", "args": {"answer": _as_text(response.content)}}

    log.info("agent.plan", node="plan_action", tool=last["name"])
    return {
        **state,
        "last_tool_call": last,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "estimated_cost_usd": estimate_cost_usd(tokens_input, tokens_output),
    }


def _append(state: AgentState, description: str, action: str, result: str, is_error: bool) -> list:
    history = list(state.get("action_history", []))
    history.append(
        {"description": description, "action": action, "result": result, "is_error": is_error}
    )
    return history


def node_execute_action(state: AgentState) -> AgentState:
    """act + observe: run the chosen tool; errors become recoverable history entries."""
    log = _logger(state)
    call = state["last_tool_call"]
    name = call["name"]
    args = call.get("args", {})
    dataset_id = state["dataset_id"]
    updates: dict[str, Any] = {}

    if name == "inspect_schema":
        description = "Inspecting the dataset's tables and columns."
        with span("tool.inspect_schema"):
            result = tool_inspect_schema(dataset_id)
        is_error = result.startswith("ERROR:")
        action = "inspect_schema()"
    elif name == "run_sql":
        sql = args.get("sql", "")
        description = f"Querying the data: {_describe_sql(sql)}"
        with span("tool.run_sql"):
            result = tool_run_sql(dataset_id, sql)
        is_error = result.startswith("ERROR:")
        action = sql
        if not is_error:
            try:
                updates["result_table"] = json.loads(result)
            except json.JSONDecodeError:
                pass
    elif name == "suggest_chart":
        ctype = args.get("chart_type", "")
        x = args.get("x_column", "")
        y = args.get("y_column", "")
        title = args.get("title", "")
        description = f"Building a {ctype or 'chart'} of {y or '?'} by {x or '?'}."
        with span("tool.suggest_chart"):
            result, chart = tool_suggest_chart(state.get("result_table"), ctype, x, y, title)
        is_error = result.startswith("ERROR:")
        action = f"suggest_chart(type={ctype}, x={x}, y={y})"
        if chart is not None:
            updates["chart"] = chart
    else:
        description = f"Unknown tool '{name}'."
        result = f"ERROR: unknown tool '{name}'"
        action = name
        is_error = True

    log.info("agent.act", node="execute_action", tool=name, is_error=is_error)
    truncated = result[:_RESULT_PREVIEW_CHARS]
    return {
        **state,
        **updates,
        "action_history": _append(state, description, action, truncated, is_error),
    }


def _describe_sql(sql: str) -> str:
    flat = " ".join(sql.split())
    return flat if len(flat) <= 120 else flat[:117] + "..."


def node_finalize(state: AgentState) -> AgentState:
    """The model called finish — set the answer + result table from its args."""
    args = state["last_tool_call"].get("args", {})
    answer = _as_text(args.get("answer", "")) or "Done."
    result_table = state.get("result_table")  # carried from the last successful run_sql
    _logger(state).info("run.complete", node="finalize",
                        tokens_input=state.get("tokens_input"),
                        tokens_output=state.get("tokens_output"))
    return {**state, "final_answer": answer, "result_table": result_table,
            "chart": state.get("chart")}


def node_force_finalize(state: AgentState) -> AgentState:
    """Iterations exhausted — synthesise the best answer from history (never a bare fail)."""
    log = _logger(state)
    history_text = "\n".join(
        f"- {s['description']} → {s['result']}" for s in state.get("action_history", [])
    ) or "(no successful steps)"
    prompt = load("force_finalize").format(
        question=state["question"], history=history_text
    )
    try:
        with span("gemini.force_finalize"):
            response = get_model().invoke(prompt)
        answer = _as_text(response.content) or "I could not fully answer within the step limit."
        tin, tout = usage_from_response(response)
    except Exception as exc:
        log.error("run.error", node="force_finalize", error=str(exc))
        answer = (
            "I ran out of analysis steps before fully answering. "
            "Here is what I found: "
            + (state.get("action_history", [{}])[-1].get("result", "") if state.get("action_history") else "")
        )
        tin = tout = 0

    tokens_input = state.get("tokens_input", 0) + tin
    tokens_output = state.get("tokens_output", 0) + tout
    log.info("run.complete", node="force_finalize", early_exit_reason="max_iterations")
    return {
        **state,
        "final_answer": answer,
        "early_exit_reason": "max_iterations",
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "estimated_cost_usd": estimate_cost_usd(tokens_input, tokens_output),
    }


def node_handle_error(state: AgentState) -> AgentState:
    """Fatal failure — surfaced by the runner as an api_error. DuckDB engine kept."""
    _logger(state).error("run.error", node="handle_error", error=state.get("error"))
    return state
