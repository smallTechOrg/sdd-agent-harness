"""Local schema profiling — the schema_summary side of the privacy boundary.

``build_schema_summary`` is the ONLY function that produces the schema payload
sent to the LLM (via ``plan_compute``). It returns column-level metadata and
scalar aggregates (counts, distinct counts, null counts, numeric min/max) only.
It NEVER returns raw cell values or sample rows.
"""

from __future__ import annotations

from tools import duckdb_store

# DuckDB type-name prefixes that we treat as numeric for the schema summary.
_NUMERIC_PREFIXES = (
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "DECIMAL",
    "NUMERIC",
    "REAL",
    "FLOAT",
    "DOUBLE",
)


def _summary_type(duckdb_type: str) -> str:
    """Map a DuckDB column type to the schema_summary type vocabulary."""
    t = duckdb_type.upper()
    if t.startswith(_NUMERIC_PREFIXES):
        return "number"
    if t in ("DATE",) or t.startswith("TIMESTAMP") or t.startswith("TIME"):
        return "date"
    if t == "BOOLEAN":
        return "boolean"
    return "text"


def build_schema_summary(dataset_id: str) -> dict:
    """Return the schema_summary for a locally-stored dataset.

    Shape (exactly as spec/data.md):

        {
          "row_count": int,
          "columns": [
            {"name": str, "type": "text"|"number"|...,
             "distinct": int, "nulls": int,
             "min"?: <number>, "max"?: <number>},
            ...
          ]
        }

    Only column-level scalar aggregates are computed (COUNT, COUNT DISTINCT,
    null count, and min/max for numeric columns). No raw cell values, no sample
    rows. This is a privacy-boundary payload.
    """
    name = duckdb_store.table_name(dataset_id)
    if not duckdb_store.table_exists(dataset_id):
        raise ValueError(f"No working table for dataset_id {dataset_id!r}")

    con = duckdb_store.get_connection()
    row_count = int(con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])

    columns: list[dict] = []
    for col_name, duckdb_type in duckdb_store.column_types(dataset_id):
        summary_type = _summary_type(duckdb_type)
        quoted = '"' + col_name.replace('"', '""') + '"'

        distinct, nulls = con.execute(
            f'SELECT COUNT(DISTINCT {quoted}), '
            f'COUNT(*) - COUNT({quoted}) FROM {name}'
        ).fetchone()

        col: dict = {
            "name": col_name,
            "type": summary_type,
            "distinct": int(distinct),
            "nulls": int(nulls),
        }

        if summary_type == "number":
            min_v, max_v = con.execute(
                f"SELECT MIN({quoted}), MAX({quoted}) FROM {name}"
            ).fetchone()
            if min_v is not None:
                col["min"] = _coerce_number(min_v)
            if max_v is not None:
                col["max"] = _coerce_number(max_v)

        columns.append(col)

    return {"row_count": row_count, "columns": columns}


def _coerce_number(value):
    """Coerce a DuckDB numeric scalar to a plain int/float for JSON."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    return int(f) if f.is_integer() else f
