"""DuckDB — the analytical store for the user's uploaded data.

Two access paths, deliberately separated (the action-safety boundary, harness/patterns/guardrails-and-hitl.md):
  - ingest_file()  uses a READ-WRITE connection — server-only, never exposed to the agent.
  - dataset_schema() / run_query()  use a READ-ONLY connection (read_only=True) — what the agent's tools call.
Each dataset is its own DuckDB file under settings.data_dir. DuckDB reads CSV/JSON natively and flattens
top-level JSON keys into columns on ingest.
"""
import os
import re
import sqlite3
from decimal import Decimal

import duckdb

from .config import get_settings

_IDENT_RE = re.compile(r"[^0-9a-zA-Z_]+")


def _data_dir() -> str:
    d = get_settings().data_dir
    os.makedirs(d, exist_ok=True)
    return d


def dataset_path(dataset_id: str) -> str:
    return os.path.join(_data_dir(), f"{dataset_id}.duckdb")


def sanitize_table_name(name: str) -> str:
    """A filename → a safe SQL identifier (letters/digits/underscore, not starting with a digit)."""
    base = os.path.splitext(os.path.basename(name))[0]
    ident = _IDENT_RE.sub("_", base).strip("_").lower() or "table"
    if ident[0].isdigit():
        ident = f"t_{ident}"
    return ident[:60]


def _jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, Decimal):
        return float(v)
    return str(v)


def ingest_file(dataset_id: str, table_name: str, src_path: str, filename: str) -> dict:
    """Load one CSV/JSON file into a DuckDB table (write-connection). Returns table metadata.

    Raises ValueError on a malformed/unsupported file — the caller returns a clean error and the dataset's
    existing tables are untouched (only this one CREATE is attempted).
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        reader = "read_csv_auto"
    elif ext in (".json", ".ndjson", ".jsonl"):
        reader = "read_json_auto"
    else:
        raise ValueError(f"unsupported file type '{ext}' (supported: .csv, .json)")

    safe_path = src_path.replace("'", "''")
    table = sanitize_table_name(table_name)
    con = duckdb.connect(dataset_path(dataset_id))   # read-write — server-only
    try:
        try:
            con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM {reader}(\'{safe_path}\')')
        except duckdb.Error as e:
            raise ValueError(f"could not parse '{filename}': {e}") from e
        desc = con.execute(f'DESCRIBE "{table}"').fetchall()
        columns = [{"name": r[0], "type": r[1]} for r in desc]
        n_rows = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    finally:
        con.close()
    return {"table_name": table, "filename": filename, "n_rows": int(n_rows),
            "n_cols": len(columns), "columns": columns}


def _dataset_names() -> dict[str, str]:
    """Read dataset id→name from the SQLite metadata DB (synchronous plain sqlite3)."""
    db_url = get_settings().database_url
    db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "").lstrip("./")
    if not db_path or not os.path.exists(db_path):
        return {}
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT id, name FROM datasets").fetchall()
        con.close()
        return {row[0]: row[1] for row in rows}
    except sqlite3.Error:
        return {}


def list_all_datasets() -> list[dict]:
    """Return a lightweight list of all uploaded datasets with their tables + row counts.

    Used by the list_datasets tool so the agent can see what's been uploaded.
    """
    d = _data_dir()
    results = []
    if not os.path.isdir(d):
        return results
    names = _dataset_names()
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".duckdb"):
            continue
        ds_id = fname[:-7]
        path = os.path.join(d, fname)
        try:
            con = duckdb.connect(path, read_only=True)
            tnames = [r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' ORDER BY table_name").fetchall()]
            tables = []
            for t in tnames:
                n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                tables.append({"table": t, "n_rows": int(n)})
            con.close()
            results.append({"id": ds_id, "name": names.get(ds_id, ds_id), "tables": tables})
        except duckdb.Error:
            pass
    return results


def dataset_schema(dataset_id: str) -> dict:
    """All tables in the dataset with columns + a few sample rows (read-only). For the get_schema tool."""
    path = dataset_path(dataset_id)
    if not os.path.exists(path):
        return {"tables": []}
    con = duckdb.connect(path, read_only=True)
    try:
        tnames = [r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name").fetchall()]
        tables = []
        for t in tnames:
            desc = con.execute(f'DESCRIBE "{t}"').fetchall()
            cols = [{"name": r[0], "type": r[1]} for r in desc]
            sample = con.execute(f'SELECT * FROM "{t}" LIMIT 3').fetchall()
            sample_rows = [[_jsonable(v) for v in row] for row in sample]
            tables.append({"table": t, "columns": cols, "sample_rows": sample_rows})
        return {"tables": tables}
    finally:
        con.close()


def run_query(dataset_id: str, sql: str, max_rows: int) -> dict:
    """Execute one read-only SQL statement against the dataset (read_only connection). Caps rows.

    Returns {columns, rows, row_count, truncated} or {error}. The read_only connection is the hard
    guarantee that no write/DDL can land here; the statement allowlist (agent/guardrails.py) is checked
    before this is ever called.
    """
    path = dataset_path(dataset_id)
    if not os.path.exists(path):
        return {"error": "this dataset has no tables yet — upload a file first"}
    con = duckdb.connect(path, read_only=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows = [[_jsonable(v) for v in r] for r in fetched[:max_rows]]
        return {"columns": cols, "rows": rows, "row_count": len(rows), "truncated": truncated}
    except duckdb.Error as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        con.close()
