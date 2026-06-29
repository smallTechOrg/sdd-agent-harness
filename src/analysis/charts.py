"""Deterministic chart-spec selection from an aggregate result's shape.

Privacy boundary: the chart spec is derived ONLY from the aggregate result rows
(the same rows the answer node already received) and the schema — never raw
source rows, and never via an LLM call. The spec is a small declarative object
the frontend renders client-side.

Spec shape::

    {"type": "bar"|"line"|"scatter", "x": <col>, "y": <col>,
     "series": <col>|None, "title": <short str>}

Returns ``None`` (not chartable) for a single scalar, an empty result, or any
ambiguity — never raises.
"""
from __future__ import annotations

from observability.events import get_logger

log = get_logger("charts")

# DuckDB numeric type names (eligible to be a chart's y-axis / numeric measure).
_NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
    "FLOAT", "DOUBLE", "REAL", "DECIMAL",
}
# Date/time-like type names (a temporal x-axis prefers a line chart).
_TEMPORAL_TYPES = {"DATE", "TIME", "TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS",
                   "TIMESTAMP_NS", "TIMESTAMP WITH TIME ZONE", "DATETIME"}

# Above this many categories a bar chart is dense; we still emit a spec and let
# the frontend cap/scroll — only genuinely-unusable shapes return None.
_MAX_CATEGORIES = 50


def _base_type(name: str) -> str:
    return (name or "").upper().split("(")[0].strip()


def _looks_numeric(values: list) -> bool:
    """A column whose non-null values are all numeric (int/float)."""
    seen = False
    for v in values:
        if v is None:
            continue
        seen = True
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
    return seen


def _looks_temporal(name: str, schema_types: dict, values: list) -> bool:
    if _base_type(schema_types.get(name, "")) in _TEMPORAL_TYPES:
        return True
    # Heuristic: ISO-date-like strings (e.g. "2024-01-05" from DuckDB DATE cast).
    sample = next((v for v in values if v is not None), None)
    if isinstance(sample, str) and len(sample) >= 8:
        head = sample[:10]
        if head.count("-") == 2 and head[:4].isdigit():
            return True
    return False


def choose_chart(
    question: str, result_rows: list[dict] | None, schema: list[dict] | None
) -> dict | None:
    """Pick a chart spec from the aggregate result shape, or ``None``.

    Rules:
    - empty result, or a single scalar (1 row / 1 numeric column) -> ``None``
    - one label column + one numeric column -> ``line`` if the label is
      temporal, else ``bar``
    - two numeric columns -> ``scatter``
    - otherwise (ambiguous / unusable) -> ``None``
    """
    try:
        return _choose_chart(question, result_rows or [], schema or [])
    except Exception as exc:  # defensive: a chart must never break a run
        log.warning("chart.choose_error", error=str(exc))
        return None


def _choose_chart(
    question: str, rows: list[dict], schema: list[dict]
) -> dict | None:
    if not rows:
        return None

    columns = list(rows[0].keys())
    if not columns:
        return None

    schema_types = {c.get("name"): c.get("type", "") for c in schema}
    col_values = {c: [r.get(c) for r in rows] for c in columns}
    numeric_cols = [c for c in columns if _looks_numeric(col_values[c])]
    non_numeric_cols = [c for c in columns if c not in numeric_cols]

    title = _title(question)

    # Single scalar (one row, one numeric column) -> not chartable.
    if len(rows) == 1 and len(columns) == 1 and len(numeric_cols) == 1:
        return None
    # Single row, no grouping dimension -> a bar of one point is not useful.
    if len(rows) == 1 and not non_numeric_cols:
        return None

    # Two numeric columns -> scatter (x vs y), regardless of row count.
    if len(numeric_cols) >= 2 and len(non_numeric_cols) == 0:
        return {
            "type": "scatter",
            "x": numeric_cols[0],
            "y": numeric_cols[1],
            "series": None,
            "title": title,
        }

    # One label column + at least one numeric column -> bar/line.
    if len(non_numeric_cols) >= 1 and len(numeric_cols) >= 1:
        if len(rows) > _MAX_CATEGORIES and len(non_numeric_cols) == 1:
            # Many categories: still chartable; frontend caps. Keep as bar.
            pass
        label = non_numeric_cols[0]
        measure = numeric_cols[0]
        series = non_numeric_cols[1] if len(non_numeric_cols) >= 2 else None
        chart_type = (
            "line"
            if _looks_temporal(label, schema_types, col_values[label])
            else "bar"
        )
        return {
            "type": chart_type,
            "x": label,
            "y": measure,
            "series": series,
            "title": title,
        }

    return None


def _title(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "Result"
    # Keep titles short for the chart header.
    return q if len(q) <= 80 else q[:77].rstrip() + "..."
