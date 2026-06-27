"""In-process DuckDB analytical engine.

This is the privacy boundary for user data: the full dataset lives here on the
local machine and never leaves the process. Only schema (column names + types)
and a small bounded sample of rows are ever surfaced for the LLM context.

A single process-global connection is opened against the configured DuckDB file.
Query execution is guarded (read-only single SELECT) and row-capped.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import duckdb

from config.settings import get_settings
from observability.events import get_logger
from analytics.sql_guard import assert_read_only_select

log = get_logger("analytics.duckdb")

_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def _resolve_db_path() -> Path:
    path = Path(get_settings().duckdb_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the process-global DuckDB connection (opened lazily)."""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                db_path = _resolve_db_path()
                try:
                    _conn = duckdb.connect(str(db_path))
                    log.info("duckdb_connected", db_path=str(db_path))
                except Exception as exc:  # pragma: no cover - connect failure is rare
                    log.error("duckdb_connect_failed", db_path=str(db_path), error=str(exc))
                    raise
    return _conn


def reset_connection() -> None:
    """Close and forget the global connection (used by tests for isolation)."""
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # pragma: no cover
                pass
            _conn = None


def introspect(table: str) -> dict[str, Any]:
    """Return ``{"schema": [{"column","type"}], "sample_rows": [...]}``.

    Only the schema and ``sample_row_count`` rows are returned — never the full
    table. Used to build the bounded LLM context.
    """
    settings = get_settings()
    sample_n = settings.sample_row_count
    conn = get_connection()

    try:
        schema_rows = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        schema = [{"column": r[0], "type": r[1]} for r in schema_rows]

        if not schema:
            raise ValueError(f"Table {table!r} not found in DuckDB.")

        # Sample is bounded by sample_row_count — the full table never leaves here.
        sample_cur = conn.execute(f'SELECT * FROM "{table}" LIMIT {int(sample_n)}')
        sample_cols = [d[0] for d in sample_cur.description]
        sample_rows = [list(row) for row in sample_cur.fetchall()]

        log.info(
            "duckdb_introspect",
            table=table,
            columns=len(schema),
            sample_rows=len(sample_rows),
        )
        return {
            "schema": schema,
            "sample_columns": sample_cols,
            "sample_rows": sample_rows,
        }
    except Exception as exc:
        log.error("duckdb_introspect_failed", table=table, error=str(exc))
        raise


def run_select(sql: str) -> dict[str, Any]:
    """Execute a guarded read-only SELECT and return bounded columns + rows.

    The SQL guard is re-asserted here (defence in depth). The row cap from
    ``result_row_cap`` bounds memory and the response payload.
    """
    assert_read_only_select(sql)
    cap = int(get_settings().result_row_cap)
    conn = get_connection()

    try:
        # cursor() gives an isolated result cursor without mutating shared state.
        cur = conn.cursor()
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        raw = cur.fetchmany(cap)
        rows = [list(r) for r in raw]
        log.info("duckdb_run_select", row_count=len(rows), capped=(len(rows) >= cap))
        return {"columns": columns, "rows": rows}
    except Exception as exc:
        log.error("duckdb_run_select_failed", error=str(exc))
        raise
