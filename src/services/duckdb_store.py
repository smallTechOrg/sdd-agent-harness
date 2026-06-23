"""DuckDB data-store layer.

The data store holds the *actual dataset rows* — one DuckDB table per uploaded
dataset. Raw rows live here and never enter the metadata DB or an LLM prompt
(beyond capped samples). Every public function uses a per-call connection that is
always closed, and creates the parent directory of the DuckDB file if missing.
"""
from __future__ import annotations

import os
import re
import time
from uuid import uuid4

import duckdb
import pandas as pd


class DuckDBError(RuntimeError):
    """Raised when a DuckDB operation fails (ingest, schema, sample, query)."""


def _ensure_parent_dir(duckdb_path: str) -> None:
    parent = os.path.dirname(os.path.abspath(duckdb_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def sanitize_table_name(name: str) -> str:
    """Return a safe, unique DuckDB table name like ``dataset_<shortid>``.

    The human-readable stem of ``name`` is slugged into the identifier purely
    for readability; uniqueness comes from an appended short uuid, so two
    uploads of the same filename never collide.
    """
    stem = os.path.splitext(os.path.basename(name or ""))[0]
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", stem).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    short = uuid4().hex[:8]
    if slug:
        slug = slug[:40]
        return f"dataset_{slug}_{short}"
    return f"dataset_{short}"


def _quote_ident(name: str) -> str:
    """Quote a DuckDB identifier safely (double-quotes, escaped)."""
    return '"' + str(name).replace('"', '""') + '"'


def ingest_dataframe(df: pd.DataFrame, table_name: str, duckdb_path: str) -> int:
    """Create/replace a DuckDB table from a pandas DataFrame; return row count."""
    _ensure_parent_dir(duckdb_path)
    con = None
    try:
        con = duckdb.connect(duckdb_path)
        # Register the frame and materialise it as a persistent table.
        con.register("_ingest_df", df)
        con.execute(
            f"CREATE OR REPLACE TABLE {_quote_ident(table_name)} AS "
            f"SELECT * FROM _ingest_df"
        )
        con.unregister("_ingest_df")
        result = con.execute(
            f"SELECT COUNT(*) FROM {_quote_ident(table_name)}"
        ).fetchone()
        return int(result[0]) if result else 0
    except Exception as exc:  # noqa: BLE001 - re-raised as a clear domain error
        raise DuckDBError(f"Failed to ingest table '{table_name}': {exc}") from exc
    finally:
        if con is not None:
            con.close()


def get_schema(table_name: str, duckdb_path: str) -> list[dict[str, str]]:
    """Return column descriptors ``[{name, type}]`` for a DuckDB table."""
    con = None
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        rows = con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? ORDER BY ordinal_position",
            [table_name],
        ).fetchall()
        return [{"name": str(r[0]), "type": str(r[1])} for r in rows]
    except Exception as exc:  # noqa: BLE001
        raise DuckDBError(
            f"Failed to read schema for table '{table_name}': {exc}"
        ) from exc
    finally:
        if con is not None:
            con.close()


def get_sample_rows(
    table_name: str, duckdb_path: str, limit: int
) -> list[list]:
    """Return up to ``limit`` rows as a list-of-lists.

    Token-economy guard: this NEVER returns more than ``limit`` rows.
    """
    safe_limit = max(0, int(limit))
    con = None
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        rows = con.execute(
            f"SELECT * FROM {_quote_ident(table_name)} LIMIT ?",
            [safe_limit],
        ).fetchall()
        capped = rows[:safe_limit]
        return [list(r) for r in capped]
    except Exception as exc:  # noqa: BLE001
        raise DuckDBError(
            f"Failed to sample rows from table '{table_name}': {exc}"
        ) from exc
    finally:
        if con is not None:
            con.close()


_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|"
    r"replace|truncate|grant|revoke|pragma|install|load|export|import)\b",
    re.IGNORECASE,
)


def _assert_read_only(sql: str) -> str:
    """Validate a single read-only SELECT/WITH statement; return it stripped."""
    stripped = (sql or "").strip().rstrip(";").strip()
    if not stripped:
        raise DuckDBError("Empty SQL statement.")
    if ";" in stripped:
        raise DuckDBError("Only a single SQL statement is allowed.")
    lowered = stripped.lstrip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise DuckDBError("Only read-only SELECT statements are allowed.")
    if _WRITE_KEYWORDS.search(stripped):
        raise DuckDBError("Only read-only SELECT statements are allowed.")
    return stripped


def execute_select(
    sql: str, duckdb_path: str, display_limit: int
) -> tuple[list[str], list[list], int, int]:
    """Run a read-only SELECT.

    Returns ``(columns, rows_capped_to_display_limit, full_row_count, duration_ms)``.
    The connection is opened read-only so no write can ever occur, and the SQL is
    validated as a single SELECT/WITH before execution.
    """
    statement = _assert_read_only(sql)
    cap = max(0, int(display_limit))
    con = None
    started = time.perf_counter()
    try:
        con = duckdb.connect(duckdb_path, read_only=True)
        cur = con.execute(statement)
        columns = [d[0] for d in cur.description] if cur.description else []
        all_rows = cur.fetchall()
        duration_ms = int((time.perf_counter() - started) * 1000)
        full_row_count = len(all_rows)
        capped = [list(r) for r in all_rows[:cap]]
        return columns, capped, full_row_count, duration_ms
    except DuckDBError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DuckDBError(f"Query execution failed: {exc}") from exc
    finally:
        if con is not None:
            con.close()
