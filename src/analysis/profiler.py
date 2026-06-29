"""Per-column dataset profiling, computed entirely in local DuckDB.

Privacy boundary (hard invariant): profiling runs aggregate-only queries against
the per-dataset DuckDB file. It emits per-column *statistics* (null/distinct
counts, numeric min/max, data-quality flags) — NEVER raw rows. The result is the
only thing that may later feed a prompt or the API response.

Non-fatal by design: a per-column query error is logged and that column gets a
partial entry (with an ``error`` flag) so a single bad column never fails the
whole upload.
"""
from __future__ import annotations

import duckdb

from observability.events import get_logger

log = get_logger("profiler")

TABLE_NAME = "data"

# DuckDB type names that are numeric (eligible for min/max as numbers).
_NUMERIC_TYPES = {
    "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
    "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT",
    "FLOAT", "DOUBLE", "REAL", "DECIMAL",
}

# Threshold above which a column is flagged as high-null (fraction of rows null).
_HIGH_NULL_FRACTION = 0.5


def _is_numeric(duckdb_type: str) -> bool:
    base = (duckdb_type or "").upper().split("(")[0].strip()
    return base in _NUMERIC_TYPES


def _jsonable(value):
    """Coerce a DuckDB scalar to a JSON-serialisable Python value."""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def profile_dataset(
    duckdb_path: str, schema: list[dict], *, table_name: str = TABLE_NAME
) -> list[dict]:
    """Compute a per-column profile from the dataset's DuckDB file.

    Returns a list of ``{column, type, null_count, distinct_count, min, max,
    flags}`` entries — one per schema column. ``min``/``max`` are populated only
    for numeric columns (``None`` otherwise). ``flags`` is a list drawn from
    ``all_null``, ``constant``, ``high_null`` (and ``error`` on a per-column
    failure). Aggregate-only — no raw rows leave DuckDB.
    """
    profile: list[dict] = []
    con = None
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        try:
            row_count = con.execute(
                f"SELECT count(*) FROM {table_name}"
            ).fetchone()[0]
        except duckdb.Error:
            row_count = 0

        for col in schema or []:
            name = col.get("name", "")
            col_type = col.get("type", "")
            entry = _profile_column(con, table_name, name, col_type, row_count)
            profile.append(entry)
    except duckdb.Error as exc:
        # Connection-level failure — return whatever (likely nothing) we built.
        log.error("profile.failed", duckdb_path=duckdb_path, error=str(exc))
    finally:
        if con is not None:
            con.close()
    return profile


def _profile_column(
    con: "duckdb.DuckDBPyConnection",
    table: str,
    name: str,
    col_type: str,
    row_count: int,
) -> dict:
    """Profile a single column. Non-fatal: returns a partial entry on error."""
    entry: dict = {
        "column": name,
        "type": col_type,
        "null_count": None,
        "distinct_count": None,
        "min": None,
        "max": None,
        "flags": [],
    }
    # Double-quote the identifier to tolerate spaces / reserved words.
    ident = '"' + name.replace('"', '""') + '"'
    numeric = _is_numeric(col_type)
    try:
        if numeric:
            sql = (
                f"SELECT count(*) - count({ident}), "
                f"count(DISTINCT {ident}), "
                f"min({ident}), max({ident}) FROM {table}"
            )
            null_count, distinct_count, col_min, col_max = con.execute(
                sql
            ).fetchone()
            entry["min"] = _jsonable(col_min)
            entry["max"] = _jsonable(col_max)
        else:
            sql = (
                f"SELECT count(*) - count({ident}), "
                f"count(DISTINCT {ident}) FROM {table}"
            )
            null_count, distinct_count = con.execute(sql).fetchone()

        entry["null_count"] = int(null_count)
        entry["distinct_count"] = int(distinct_count)
        entry["flags"] = _quality_flags(
            int(null_count), int(distinct_count), row_count
        )
    except duckdb.Error as exc:
        log.warning("profile.column_error", column=name, error=str(exc))
        entry["flags"] = ["error"]
    return entry


def _quality_flags(null_count: int, distinct_count: int, row_count: int) -> list[str]:
    flags: list[str] = []
    if row_count > 0 and null_count >= row_count:
        flags.append("all_null")
    if distinct_count <= 1:
        flags.append("constant")
    if row_count > 0 and (null_count / row_count) > _HIGH_NULL_FRACTION:
        flags.append("high_null")
    return flags
