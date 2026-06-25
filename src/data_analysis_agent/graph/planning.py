from __future__ import annotations

import json
from collections import defaultdict

from data_analysis_agent.graph.state import AgentState

# Prompt tag the stub provider branches on — must not change without updating stub.py.
_PLAN_TAG = "<node:plan_action>"


def build_plan_prompt(state: AgentState, tools: list[dict], column_names: list[str]) -> str:
    """Assemble the full plan_action prompt for the current ReAct turn.

    Concatenates the intro, available-tools block, dataset schema, the user question,
    prior tool-call history, and the response-format instructions. Tools and schema are
    supplied by the caller (read from the session's pool), not stored in state.

    Args:
        state: The current agent state carrying the question and history.
        tools: The session's MCP tool descriptors (from ``SessionPoolManager``).
        column_names: The ``table.column`` schema for the session's sources.

    Returns:
        The complete prompt string sent to the LLM.
    """
    lines = _intro_lines()
    lines += _tools_lines(tools)
    lines += _schema_lines(column_names)
    lines.append(f"User question: {state['question']}")
    lines += _history_lines(state.get("action_history", []))
    lines += _response_format_lines()
    return "\n".join(lines)


def _intro_lines() -> list[str]:
    """Return the static ReAct-loop introduction and DuckDB dialect notes."""
    return [
        _PLAN_TAG,
        "You are a data-analysis agent operating in a ReAct (Reason + Act) loop.",
        "On each turn you either (a) call a tool to gather more data, or (b) give the",
        "final answer. After each tool call you will see its result and may call another",
        "tool. Build up a plan across multiple queries — and across multiple tables when",
        "more than one data source is attached — until you can answer the question.",
        "",
        "SQL dialect: DuckDB. Notes:",
        "- Aggregates available natively: COUNT, SUM, AVG, MIN, MAX, STDDEV, VARIANCE, MEDIAN, QUANTILE.",
        "- Use SQRT/ABS/ROUND for math.",
        "- Only SELECT statements are permitted.",
        "- If a column is numeric but stored as text, CAST(col AS DOUBLE) before aggregating.",
        "",
    ]


def _tools_lines(tools: list[dict]) -> list[str]:
    """Return the available-tools block, or an empty list when no tools are loaded."""
    if not tools:
        return []
    lines = ["Available tools (call a tool by its exact name):", ""]
    for tool in tools:
        table = tool.get("table_name")
        suffix = f" (queries table: {table})" if table else ""
        lines.append(f"Tool: {tool['name']}{suffix}")
        lines.append(f"  Description: {tool.get('description', '')}")
        lines.append(f"  Parameters: {json.dumps(tool.get('parameter_schema', {}))}")
        lines.append("")
    return lines


def _schema_lines(column_names: list[str]) -> list[str]:
    """Return the dataset schema block, grouping ``table.column`` names by table."""
    table_cols: dict[str, list[str]] = defaultdict(list)
    for col in column_names:
        if "." in col:
            table, name = col.split(".", 1)
            table_cols[table].append(name)
        else:
            table_cols["data"].append(col)

    lines = [f"Dataset schema ({len(table_cols)} table(s) — query each by its exact name):"]
    for table, cols in table_cols.items():
        lines.append(f"  Table: {table} — Columns: {', '.join(cols)}")
    lines.append("")
    return lines


def _history_lines(history: list[dict]) -> list[str]:
    """Return the prior tool-call trace, or an empty list when there is no history."""
    if not history:
        return []
    lines = ["", "Previous tool calls and results:"]
    for i, entry in enumerate(history, 1):
        lines.append(f'[{i}] tool: {entry["tool"]}')
        lines.append(f'    arguments: {json.dumps(entry["arguments"])}')
        if entry.get("is_error"):
            lines.append(f'    result: Error: {entry["result"]}')
            lines.append("    → This call failed. Please write a corrected query.")
        else:
            lines.append(f'    result:\n{entry["result"]}')
    return lines


def _response_format_lines() -> list[str]:
    """Return the closing instructions that define the tool-call / FINAL ANSWER format."""
    return [
        "",
        "Decide your next step. Respond with EXACTLY ONE of the following, and nothing else",
        "(no explanations, no markdown, no backticks):",
        "",
        "1. A JSON tool call to gather more data:",
        '   {"tool": "<tool_name>", "arguments": {"query": "SELECT ..."}}',
        "   ('tool' MUST be one of the exact tool names listed above.)",
        "",
        "2. The final answer, when you have enough information:",
        "   FINAL ANSWER: <your complete answer here>",
    ]
