"""Local DuckDB query execution.

This module is the ONLY component that touches raw uploaded rows. It runs
generated SQL against a per-dataset DuckDB file read-only and returns a capped
result set. A query error is captured verbatim and returned (not raised) so the
agent's retry-on-SQL-error edge can feed the message back to the model.
"""
from __future__ import annotations

import duckdb

# Cap on result rows carried back from a query. Aggregate answers are tiny; this
# guards against a model emitting a raw-row SELECT that would bloat the result.
MAX_RESULT_ROWS = 1000


def run_query(
    duckdb_path: str, sql: str, *, max_rows: int = MAX_RESULT_ROWS
) -> tuple[list[dict], str | None]:
    """Run SQL read-only against the dataset's DuckDB file.

    Returns ``(rows, None)`` on success (rows capped at ``max_rows``) or
    ``([], error_message)`` on a DuckDB error. Never raises for a query error.
    """
    con = None
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        cursor = con.execute(sql)
        columns = [c[0] for c in cursor.description] if cursor.description else []
        raw_rows = cursor.fetchmany(max_rows)
        rows = [dict(zip(columns, _normalize(r))) for r in raw_rows]
        return rows, None
    except duckdb.Error as exc:
        return [], str(exc)
    finally:
        if con is not None:
            con.close()


def _normalize(row: tuple) -> list:
    """Coerce DuckDB scalar types to JSON-serializable Python values."""
    out = []
    for v in row:
        if isinstance(v, (int, float, str, bool)) or v is None:
            out.append(v)
        else:
            # Decimal, date, datetime, etc. -> string for safe JSON/transport.
            out.append(str(v))
    return out
