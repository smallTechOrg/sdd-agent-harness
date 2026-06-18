"""Real MCP server (stdio) exposing the dataset query tools (layer 4, MCP everywhere).

Runs as its own process; opens the dataset's file-backed DuckDB read-only and serves
`inspect_schema` and `run_sql` over MCP. Both delegate to the same read-only-safe
implementations in datachat.data.query / tools.sql_tools — one source of truth.

Run standalone:  uv run python -m datachat.mcp.servers.sql_server
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import json

from datachat.tools.sql_tools import (
    INSPECT_SCHEMA_DESC,
    RUN_SQL_DESC,
    SUGGEST_CHART_DESC,
    tool_inspect_schema,
    tool_run_sql,
    tool_suggest_chart,
)

mcp = FastMCP("datachat-sql")


@mcp.tool(description=INSPECT_SCHEMA_DESC)
def inspect_schema(dataset_id: str) -> str:
    """List the dataset's tables, columns, and types."""
    return tool_inspect_schema(dataset_id)


@mcp.tool(description=RUN_SQL_DESC)
def run_sql(dataset_id: str, sql: str) -> str:
    """Run a single read-only SELECT against the dataset and return the rows as JSON."""
    return tool_run_sql(dataset_id, sql)


@mcp.tool(description=SUGGEST_CHART_DESC + " Pass the last run_sql result as result_table_json.")
def suggest_chart(
    result_table_json: str, chart_type: str, x_column: str, y_column: str, title: str
) -> str:
    """Build a chart spec from a result table (JSON). Returns the chart JSON or an error string."""
    try:
        table = json.loads(result_table_json) if result_table_json else None
    except json.JSONDecodeError as exc:
        return f"ERROR: result_table_json is not valid JSON: {exc}"
    message, chart = tool_suggest_chart(table, chart_type, x_column, y_column, title)
    return json.dumps(chart) if chart is not None else message


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
