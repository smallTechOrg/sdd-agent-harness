"""Build a chart spec from a result table (capabilities/04-visualizations.md).

A pure transform of data the agent already retrieved via run_sql — no external system, no new
data. Returns an error value (never raises) when the requested columns/type don't fit, so the
ReAct loop can observe and self-correct.
"""

from __future__ import annotations

from typing import Any

CHART_TYPES = frozenset({"bar", "line", "pie"})


class ChartError(ValueError):
    """A bad chart request — surfaced as a recoverable action-history error value."""


def build_chart(
    result_table: dict[str, Any] | None,
    chart_type: str,
    x_column: str,
    y_column: str,
    title: str,
) -> dict[str, Any]:
    """Build {type,title,x,y,data:[{x,y}]} from the last result table.

    Raises ChartError with a model-readable reason on a bad type/column.
    """
    chart_type = (chart_type or "").strip().lower()
    if chart_type not in CHART_TYPES:
        raise ChartError(
            f"chart_type '{chart_type}' is not supported; use one of: bar, line, pie."
        )
    if not result_table or not result_table.get("columns"):
        raise ChartError("No query result is available to chart — run a query first.")

    columns = result_table["columns"]
    if x_column not in columns:
        raise ChartError(f"x_column '{x_column}' is not in the result columns {columns}.")
    if y_column not in columns:
        raise ChartError(f"y_column '{y_column}' is not in the result columns {columns}.")

    xi = columns.index(x_column)
    yi = columns.index(y_column)
    data = [{"x": row[xi], "y": row[yi]} for row in result_table["rows"]]
    if not data:
        raise ChartError("The result has no rows to chart.")

    return {"type": chart_type, "title": title or "", "x": x_column, "y": y_column, "data": data}
