"""Local aggregation + the privacy boundary guard.

This module holds the two boundary-critical pieces of DataChat:

* ``run_aggregation`` — executes a compute plan LOCALLY over the FULL dataset
  in DuckDB and returns a small, bounded grouped aggregate result. It reads all
  rows but returns only the grouped aggregate, never the raw table.

* ``assert_no_raw_rows`` — THE GUARD. It is the single chokepoint the two
  LLM-calling nodes (``plan_compute`` and ``phrase_answer``) call immediately
  before any LLM call. It rejects any payload that is not a schema_summary or a
  bounded aggregate_result, so raw rows can never reach the model.

The privacy boundary rule (spec/architecture.md): the ONLY payloads that may be
sent to the LLM are (1) a schema_summary and (2) a bounded aggregate_result.
Raw rows, individual records, full columns, or row samples must NEVER cross.
"""

from __future__ import annotations

from tools import duckdb_store

# Maximum number of grouped rows allowed in an aggregate_result that crosses the
# boundary. This keeps the result an *aggregate* and never a row dump. The same
# bound is enforced both when producing a result (run_aggregation caps + orders)
# and when guarding any LLM-bound payload (assert_no_raw_rows rejects above it).
MAX_AGGREGATE_ROWS = 50

# Allowed aggregation functions (plan.aggregation). Maps to SQL.
_AGGREGATIONS = {
    "sum": "SUM",
    "avg": "AVG",
    "count": "COUNT",
    "min": "MIN",
    "max": "MAX",
}

# A marker key a caller could set to flag a payload as carrying raw rows; the
# guard rejects any payload containing it (defence in depth).
_RAW_ROWS_MARKER = "__raw_rows__"


class PrivacyBoundaryError(Exception):
    """Raised when a payload bound for the LLM would leak raw data rows."""


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def run_aggregation(plan: dict, dataset_id: str) -> dict:
    """Execute a compute plan locally over the FULL dataset.

    ``plan`` shape (from spec/agent.md ``plan_compute``):
        {"group_by": str, "metric_column": str,
         "aggregation": "sum"|"avg"|"count"|"min"|"max", "filter"?: str}

    Returns the aggregate_result shape (spec/data.md), exactly:
        {"group_by": str, "metric": str,
         "aggregation": "sum"|"avg"|"count"|"min"|"max",
         "rows": [{<group_by>: ..., <metric>: ...}, ...]}

    The aggregation runs over ALL rows in DuckDB. The result is bounded to
    ``MAX_AGGREGATE_ROWS`` grouped rows (ordered by the metric descending) so it
    is always an aggregate, never a raw-row dump.
    """
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")

    group_by = plan.get("group_by")
    metric_column = plan.get("metric_column")
    aggregation = str(plan.get("aggregation", "")).lower()

    if not group_by:
        raise ValueError("plan.group_by is required")
    if aggregation not in _AGGREGATIONS:
        raise ValueError(
            f"Unsupported aggregation {plan.get('aggregation')!r}; "
            f"expected one of {sorted(_AGGREGATIONS)}"
        )
    # count is allowed without a metric column (counts rows per group).
    if aggregation != "count" and not metric_column:
        raise ValueError(
            f"plan.metric_column is required for aggregation {aggregation!r}"
        )

    if not duckdb_store.table_exists(dataset_id):
        raise ValueError(f"No working table for dataset_id {dataset_id!r}")

    valid_cols = {c for c, _ in duckdb_store.column_types(dataset_id)}
    if group_by not in valid_cols:
        raise ValueError(f"Unknown group_by column {group_by!r}")
    if metric_column and metric_column not in valid_cols:
        raise ValueError(f"Unknown metric_column {metric_column!r}")

    table = duckdb_store.table_name(dataset_id)
    g_ident = _quote_ident(group_by)
    sql_fn = _AGGREGATIONS[aggregation]

    if aggregation == "count" and not metric_column:
        metric_alias = "count"
        metric_expr = "COUNT(*)"
    else:
        metric_alias = metric_column
        metric_expr = f"{sql_fn}({_quote_ident(metric_column)})"

    m_out_ident = _quote_ident(metric_alias)
    sql = (
        f"SELECT {g_ident} AS {g_ident}, "
        f"{metric_expr} AS {m_out_ident} "
        f"FROM {table} "
        f"GROUP BY {g_ident} "
        f"ORDER BY {m_out_ident} DESC "
        f"LIMIT {MAX_AGGREGATE_ROWS}"
    )

    con = duckdb_store.get_connection()
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, _coerce_row(r))) for r in cur.fetchall()]

    result = {
        "group_by": group_by,
        "metric": metric_alias,
        "aggregation": aggregation,
        "rows": rows,
    }
    return result


def _coerce_row(row) -> list:
    """Coerce DuckDB scalar values to JSON-friendly Python scalars."""
    out = []
    for v in row:
        if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
            out.append(v)
        else:
            try:
                f = float(v)
                out.append(int(f) if f.is_integer() else f)
            except (TypeError, ValueError):
                out.append(str(v))
    return out


def _is_schema_summary(payload: dict) -> bool:
    return "columns" in payload and "row_count" in payload


def _is_aggregate_result(payload: dict) -> bool:
    return "rows" in payload and "aggregation" in payload and "group_by" in payload


def assert_no_raw_rows(payload: dict) -> dict:
    """Guard a payload bound for the LLM. Return it unchanged, or raise.

    This is THE privacy boundary chokepoint. It accepts ONLY:

    * a **schema_summary** — has ``columns`` + ``row_count`` and carries no
      raw-row list; or
    * a bounded **aggregate_result** — has ``group_by`` + ``aggregation`` +
      ``rows`` where ``len(rows) <= MAX_AGGREGATE_ROWS`` and each row is a
      grouped aggregate (a small dict), never the raw table.

    Anything else — a raw-rows marker, a too-large row list, a non-dict payload,
    or an unrecognised shape — raises ``PrivacyBoundaryError``. Raw data rows can
    therefore never reach the LLM.
    """
    if not isinstance(payload, dict):
        raise PrivacyBoundaryError(
            f"LLM payload must be a dict, got {type(payload).__name__}"
        )

    if _RAW_ROWS_MARKER in payload:
        raise PrivacyBoundaryError(
            "LLM payload carries a raw-rows marker; refusing to cross boundary"
        )

    is_schema = _is_schema_summary(payload)
    is_aggregate = _is_aggregate_result(payload)

    if not (is_schema or is_aggregate):
        raise PrivacyBoundaryError(
            "LLM payload is neither a schema_summary nor an aggregate_result; "
            "only schema/aggregate payloads may cross the privacy boundary"
        )

    if is_schema:
        # A schema_summary must not smuggle a list of raw rows.
        if "rows" in payload:
            raise PrivacyBoundaryError(
                "schema_summary must not contain a 'rows' list"
            )
        cols = payload.get("columns")
        if not isinstance(cols, list):
            raise PrivacyBoundaryError("schema_summary.columns must be a list")
        for col in cols:
            if not isinstance(col, dict) or "name" not in col:
                raise PrivacyBoundaryError(
                    "schema_summary.columns entries must be column descriptors"
                )
        return payload

    # aggregate_result branch.
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise PrivacyBoundaryError("aggregate_result.rows must be a list")
    if len(rows) > MAX_AGGREGATE_ROWS:
        raise PrivacyBoundaryError(
            f"aggregate_result has {len(rows)} rows, exceeding the bound of "
            f"{MAX_AGGREGATE_ROWS}; this looks like a raw-row dump, not an "
            "aggregate"
        )
    for row in rows:
        if not isinstance(row, dict):
            raise PrivacyBoundaryError(
                "aggregate_result rows must be grouped-aggregate dicts"
            )
    return payload
