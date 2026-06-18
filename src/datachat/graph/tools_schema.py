"""Tool schemas bound to Gemini for the plan_action call.

The LLM chooses among inspect_schema / run_sql / finish. `dataset_id` is NOT exposed to
the model — it is injected from AgentState at execution time. These schemas mirror the
real MCP server tools (mcp/servers/sql_server.py); execution delegates to the same
read-only-safe implementations.
"""

from __future__ import annotations

from langchain_core.tools import tool

from datachat.tools.sql_tools import (
    INSPECT_SCHEMA_DESC,
    RUN_SQL_DESC,
    SUGGEST_CHART_DESC,
)


@tool(description=INSPECT_SCHEMA_DESC)
def inspect_schema() -> str:
    """List the dataset's tables, columns, and types."""  # executed via state injection
    return ""


@tool(description=RUN_SQL_DESC)
def run_sql(sql: str) -> str:
    """Run a single read-only SELECT against the dataset (DuckDB)."""
    return ""


@tool(description=SUGGEST_CHART_DESC)
def suggest_chart(chart_type: str, x_column: str, y_column: str, title: str) -> str:
    """Attach a chart built from the last run_sql result. Skip when a chart doesn't help."""
    return ""


@tool(description="Finish: return the final plain-English answer. The result table from your last "
                  "successful run_sql is attached automatically — you do not pass it here.")
def finish(answer: str) -> str:
    """Call when you have the answer (plain English). The last query's table is attached for you."""
    return ""


TOOLS = [inspect_schema, run_sql, suggest_chart, finish]
