"""CSV ingest into a per-dataset DuckDB file.

Reads an uploaded CSV into a local DuckDB file (table name ``data``), computes
the row count, and extracts the schema as ``[{name, type}, ...]`` using DuckDB's
own column types. Raw rows live ONLY in this file and never enter an LLM prompt.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import duckdb

# ~100MB upload cap (roadmap key constraint).
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# Directory for per-dataset DuckDB files (gitignored).
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "duckdb"

TABLE_NAME = "data"


class IngestError(Exception):
    """A user-facing ingest failure (bad/empty/unparseable CSV)."""


class FileTooLargeError(Exception):
    """Upload exceeds the size limit -> maps to HTTP 413."""


def ingest_csv(filename: str, content: bytes, *, data_dir: Path | None = None) -> dict:
    """Ingest CSV ``content`` into a new per-dataset DuckDB file.

    Returns ``{duckdb_path, table_name, schema, row_count}``.
    Raises ``FileTooLargeError`` (413) or ``IngestError`` (400) on bad input.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise FileTooLargeError(
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit."
        )
    if not content.strip():
        raise IngestError("Uploaded file is empty.")

    target_dir = data_dir or _DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    duckdb_path = str(target_dir / f"{uuid.uuid4()}.duckdb")
    # Write the raw bytes to a temp CSV next to the DuckDB file for read_csv_auto.
    csv_path = duckdb_path + ".csv"
    Path(csv_path).write_bytes(content)

    con = None
    try:
        con = duckdb.connect(duckdb_path)
        # read_csv_auto infers column types; SAMPLE_SIZE=-1 scans all rows for
        # accurate type detection on the local single-user path.
        con.execute(
            f"CREATE TABLE {TABLE_NAME} AS "
            f"SELECT * FROM read_csv_auto(?, SAMPLE_SIZE=-1)",
            [csv_path],
        )
        schema = _extract_schema(con, TABLE_NAME)
        if not schema:
            raise IngestError("CSV has no columns.")
        row_count = con.execute(f"SELECT count(*) FROM {TABLE_NAME}").fetchone()[0]
    except IngestError:
        _cleanup(con, duckdb_path, csv_path)
        raise
    except duckdb.Error as exc:
        _cleanup(con, duckdb_path, csv_path)
        raise IngestError(f"Could not parse CSV: {exc}") from exc
    finally:
        if con is not None:
            con.close()

    # The CSV bytes are now materialized in DuckDB; drop the temp CSV.
    try:
        os.remove(csv_path)
    except OSError:
        pass

    return {
        "duckdb_path": duckdb_path,
        "table_name": TABLE_NAME,
        "schema": schema,
        "row_count": int(row_count),
    }


def _extract_schema(con: "duckdb.DuckDBPyConnection", table: str) -> list[dict]:
    """Schema as [{name, type}, ...] using DuckDB's own types via DESCRIBE."""
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    # DESCRIBE columns: column_name, column_type, null, key, default, extra
    return [{"name": r[0], "type": r[1]} for r in rows]


def _cleanup(con, duckdb_path: str, csv_path: str) -> None:
    if con is not None:
        try:
            con.close()
        except Exception:
            pass
    for p in (duckdb_path, csv_path):
        try:
            os.remove(p)
        except OSError:
            pass
