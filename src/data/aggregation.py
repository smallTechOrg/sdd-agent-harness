"""Local aggregation engine — the privacy firewall.

`run_plan(file_path, plan)` loads the stored file with pandas, runs the planned
group-by/aggregation entirely LOCALLY, and returns a small aggregate table.

CRITICAL INVARIANTS:
  * This module NEVER makes a network or LLM call.
  * It NEVER returns raw rows — only aggregated results, hard-capped at 50 rows.
Raw data exists here only transiently as a pandas DataFrame; nothing leaves this
module except the small aggregate table.
"""
from __future__ import annotations

import math

import pandas as pd
from pandas.api import types as ptypes

from data.schema import load_dataframe

# Hard cap on rows in any returned aggregate table, regardless of plan.limit.
MAX_ROWS = 50

_VALID_AGGS = {"sum", "mean", "count", "min", "max"}


def _require_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Plan references column(s) not in dataset: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def _jsonable(value):
    """Coerce a pandas/numpy scalar into a JSON-serialisable Python scalar."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    # numpy / pandas scalars expose .item()
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except (ValueError, TypeError):  # pragma: no cover - defensive
            return str(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    # Timestamps / dates / anything else → stable string.
    return str(value)


def run_plan(file_path: str, plan: dict) -> dict:
    """Execute an aggregation plan locally over the stored file.

    Plan shape (see spec/agent.md):
        {group_by: [col,...], metric: col|null, agg: sum|mean|count|min|max,
         filter: ..., sort: "asc"|"desc"|null, limit: int, intent: ...}

    Returns:
        {"rows": [{col: val, ...}, ...],   # small aggregate table, ≤ 50 rows
         "columns": [col names...],        # columns present in the result
         "intent": plan["intent"]}         # passed through for chart selection

    Raises ValueError if the plan references a column absent from the file or
    specifies an unknown aggregation. Never makes a network/LLM call; never
    returns raw rows.
    """
    df = load_dataframe(file_path)

    group_by = list(plan.get("group_by") or [])
    metric = plan.get("metric")
    agg = (plan.get("agg") or "count").lower()
    sort = plan.get("sort")
    intent = plan.get("intent")

    if agg not in _VALID_AGGS:
        raise ValueError(
            f"Unknown aggregation {agg!r}; expected one of {sorted(_VALID_AGGS)}"
        )

    # Validate every referenced column up front so the graph routes to handle_error.
    referenced = list(group_by)
    if metric:
        referenced.append(metric)
    _require_columns(df, referenced)

    # For non-count aggregations a numeric metric is required.
    if agg != "count" and metric:
        if not ptypes.is_numeric_dtype(df[metric]):
            raise ValueError(
                f"Aggregation {agg!r} needs a numeric metric, but column "
                f"{metric!r} is not numeric"
            )

    value_col = _compute(df, group_by, metric, agg)

    # Sort by the value column when requested.
    result = value_col
    if group_by and sort in ("asc", "desc"):
        result = result.sort_values(by=result.columns[-1], ascending=(sort == "asc"))

    # Hard cap: min(plan.limit, MAX_ROWS).
    limit = plan.get("limit")
    cap = MAX_ROWS
    if isinstance(limit, int) and limit > 0:
        cap = min(limit, MAX_ROWS)
    result = result.head(cap)

    columns = [str(c) for c in result.columns]
    rows = [
        {str(col): _jsonable(val) for col, val in record.items()}
        for record in result.to_dict(orient="records")
    ]
    return {"rows": rows, "columns": columns, "intent": intent}


def _compute(
    df: pd.DataFrame, group_by: list[str], metric: str | None, agg: str
) -> pd.DataFrame:
    """Run the aggregation and return a flat DataFrame (group cols + value col)."""
    if not group_by:
        # Scalar aggregation over the whole file → single-row table.
        value = _scalar_agg(df, metric, agg)
        col_name = _value_col_name(metric, agg)
        return pd.DataFrame([{col_name: _jsonable(value)}])

    grouped = df.groupby(group_by, dropna=False)
    col_name = _value_col_name(metric, agg)

    if agg == "count":
        series = grouped.size()
    else:
        series = getattr(grouped[metric], agg)()

    out = series.reset_index()
    out.columns = list(group_by) + [col_name]
    return out


def _scalar_agg(df: pd.DataFrame, metric: str | None, agg: str):
    if agg == "count":
        return int(len(df))
    return getattr(df[metric], agg)()


def _value_col_name(metric: str | None, agg: str) -> str:
    if agg == "count":
        return "count"
    return f"{agg}_{metric}"
