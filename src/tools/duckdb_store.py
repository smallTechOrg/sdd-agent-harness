"""Local working store for analysed rows (DuckDB).

This module is the ONLY place that ingests and holds raw data rows. The
analysed rows live here on the local machine and are never returned to any
caller outside ``src/tools/`` except through the bounded aggregate path in
``compute.py``. Schema profiling (``profile.py``) and aggregation
(``compute.py``) read from this store; nothing here hands a raw table back to
the graph, the API, or the LLM.

The DuckDB database file lives under the local ``data/`` directory (gitignored)
so rows stay on disk locally and are never transmitted.
"""

from __future__ import annotations

import os
import re
import threading

import duckdb

# Default location of the local working store. Kept under data/ (gitignored).
# Overridable via the DATACHAT_DUCKDB_PATH env var (used by tests for isolation).
_DEFAULT_DB_PATH = os.path.join("data", "working.duckdb")

_conn: duckdb.DuckDBPyConnection | None = None
_conn_path: str | None = None
_lock = threading.Lock()


def _db_path() -> str:
    return os.environ.get("DATACHAT_DUCKDB_PATH", _DEFAULT_DB_PATH)


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the process-wide DuckDB connection to the local working store.

    A single connection is reused. If the configured path changes (e.g. a test
    points DATACHAT_DUCKDB_PATH elsewhere), the connection is reopened.
    """
    global _conn, _conn_path
    with _lock:
        path = _db_path()
        if _conn is not None and _conn_path == path:
            return _conn
        if _conn is not None:
            _conn.close()
        # In-memory only when explicitly requested; otherwise ensure the dir.
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        _conn = duckdb.connect(path)
        _conn_path = path
        return _conn


def table_name(dataset_id: str) -> str:
    """Return a deterministic, SQL-safe table name for a dataset id.

    Non-alphanumeric characters are replaced with underscores and the name is
    prefixed so it is always a valid identifier. The mapping is deterministic:
    the same dataset_id always yields the same table name.
    """
    if not dataset_id or not str(dataset_id).strip():
        raise ValueError("dataset_id must be a non-empty string")
    safe = re.sub(r"[^0-9a-zA-Z]", "_", str(dataset_id))
    return f"ds_{safe}"


def load_csv(file_path: str, dataset_id: str) -> int:
    """Ingest a CSV into a local DuckDB table named for ``dataset_id``.

    Returns the number of rows ingested. Raises a clear exception when the file
    is missing or cannot be parsed. The rows stay local in DuckDB; nothing here
    returns them to the caller.
    """
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path!r}")

    name = table_name(dataset_id)
    con = get_connection()
    try:
        con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute(
            f"CREATE TABLE {name} AS "
            "SELECT * FROM read_csv_auto(?, header=true, sample_size=-1)",
            [file_path],
        )
    except duckdb.Error as exc:  # pragma: no cover - exercised via tests
        raise ValueError(f"Could not load CSV {file_path!r}: {exc}") from exc

    row_count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    return int(row_count)


def table_exists(dataset_id: str) -> bool:
    """Return True if a working table exists for the dataset id."""
    name = table_name(dataset_id)
    con = get_connection()
    row = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
        [name],
    ).fetchone()
    return row is not None


def column_types(dataset_id: str) -> list[tuple[str, str]]:
    """Return [(column_name, duckdb_type), ...] for the dataset's table.

    Internal helper for profiling. Returns only column metadata, never rows.
    """
    name = table_name(dataset_id)
    con = get_connection()
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [name],
    ).fetchall()
    if not rows:
        raise ValueError(f"No working table for dataset_id {dataset_id!r}")
    return [(str(r[0]), str(r[1])) for r in rows]


def query(sql: str, params: list | None = None) -> list[dict]:
    """Run a read query against the local store and return rows as dicts.

    INTERNAL to ``src/tools/`` only. Raw-row access must not escape this
    package; callers outside tools/ must go through the bounded aggregate path
    in ``compute.py`` or the schema path in ``profile.py``.
    """
    con = get_connection()
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
