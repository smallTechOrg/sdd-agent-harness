"""Tool registry — typed, pure functions exposed to the agent (layer 4).

These are the canonical implementations. They are exposed two ways over one protocol:
- as a real MCP server (mcp/servers/sql_server.py, stdio) for any MCP client, and
- bound to Gemini as LangChain tools in the graph (graph/nodes.py),
both delegating here so there is a single source of truth. Errors are returned as values
(strings), never raised, so the ReAct loop can observe and self-correct.
"""

from __future__ import annotations

import json

from datachat.data.chart import ChartError, build_chart
from datachat.data.query import QueryError, inspect_schema, run_sql

INSPECT_SCHEMA_DESC = (
    "List the dataset's tables with their columns and types. Call this first to learn "
    "the exact table and column names before writing SQL."
)

RUN_SQL_DESC = (
    "Run a single read-only SQL SELECT (DuckDB dialect) against the dataset's tables and "
    "return the result rows. Only SELECT / WITH...SELECT is allowed; writes are rejected. "
    "Use exact table names from inspect_schema."
)

SUGGEST_CHART_DESC = (
    "Attach a chart visualizing your LAST run_sql result. chart_type is one of bar, line, pie; "
    "x_column and y_column must be column names from that result; title is a short label. "
    "Call this when a chart helps the user (a comparison across categories, a trend, a breakdown). "
    "Skip it for a single-number answer."
)


def tool_inspect_schema(dataset_id: str) -> str:
    try:
        return json.dumps(inspect_schema(dataset_id), default=str)
    except QueryError as exc:
        return f"ERROR: {exc}"


def tool_run_sql(dataset_id: str, sql: str) -> str:
    try:
        result = run_sql(dataset_id, sql)
    except QueryError as exc:
        return f"ERROR: {exc}"
    return json.dumps(result, default=str)


def tool_suggest_chart(
    result_table: dict | None, chart_type: str, x_column: str, y_column: str, title: str
) -> tuple[str, dict | None]:
    """Build a chart from the last result table. Returns (message, chart_spec_or_None)."""
    try:
        chart = build_chart(result_table, chart_type, x_column, y_column, title)
    except ChartError as exc:
        return f"ERROR: {exc}", None
    return f"Chart ready: a {chart['type']} chart of {chart['y']} by {chart['x']}.", chart
