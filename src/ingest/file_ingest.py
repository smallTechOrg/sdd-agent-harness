"""File ingest: parse CSV/Excel → sanitize columns → write to SQLite → upsert UploadedFileRow."""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import Engine, text

from db.models import UploadedFileRow
from db.session import create_db_session

log = structlog.get_logger(__name__)

MAX_ROWS = 500_000
MAX_TABLE_NAME_LEN = 40


def _sanitize_col(name: str) -> str:
    """Lowercase, replace spaces/special chars with underscore, strip leading digits."""
    col = name.lower()
    col = re.sub(r"[^a-z0-9_]", "_", col)
    col = re.sub(r"_+", "_", col).strip("_")
    if col and col[0].isdigit():
        col = f"c_{col}"
    return col or "col"


def _table_name_from_filename(filename: str) -> str:
    """t_ + sanitized stem, max 40 chars total."""
    stem = Path(filename).stem
    sanitized = _sanitize_col(stem)
    prefix = "t_"
    max_stem_len = MAX_TABLE_NAME_LEN - len(prefix)
    return prefix + sanitized[:max_stem_len]


def ingest_file(
    file_bytes: bytes,
    filename: str,
    session_id: str,
    engine: Engine,
) -> dict:
    """
    Parse CSV or Excel file, write to SQLite, upsert UploadedFileRow.

    Returns:
        {table_name: str, row_count: int, columns: list[str]}

    Raises:
        ValueError: unsupported format, too many rows, or parse failure
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise ValueError(f"Unsupported file format: {suffix!r}. Must be .csv, .xlsx, or .xls")

    # Parse
    try:
        buf = io.BytesIO(file_bytes)
        if suffix == ".csv":
            df = pd.read_csv(buf)
        else:
            df = pd.read_excel(buf, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Failed to parse file: {exc}") from exc

    # Validate row count
    if len(df) > MAX_ROWS:
        raise ValueError(
            f"File has {len(df):,} rows which exceeds the 500,000 row limit"
        )

    # Sanitize column names
    df.columns = [_sanitize_col(str(c)) for c in df.columns]

    # Deduplicate column names (in case sanitization creates duplicates)
    seen: dict[str, int] = {}
    new_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols

    columns: list[str] = list(df.columns)
    row_count = len(df)
    table_name = _table_name_from_filename(filename)

    log.info("ingesting_file", filename=filename, table_name=table_name, row_count=row_count)

    # Write to SQLite
    try:
        with engine.connect() as conn:
            df.to_sql(table_name, con=conn, if_exists="replace", index=False)
            conn.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to write table {table_name!r}: {exc}") from exc

    # Upsert UploadedFileRow: delete existing row for same session+table, then insert
    with create_db_session() as db_session:
        existing = (
            db_session.query(UploadedFileRow)
            .filter(
                UploadedFileRow.session_id == session_id,
                UploadedFileRow.table_name == table_name,
            )
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.flush()

        file_row = UploadedFileRow(
            session_id=session_id,
            filename=filename,
            table_name=table_name,
            row_count=row_count,
            column_names=json.dumps(columns),
        )
        db_session.add(file_row)
        file_id = file_row.id

    log.info("file_ingested", table_name=table_name, row_count=row_count, file_id=file_id)

    return {
        "table_name": table_name,
        "row_count": row_count,
        "columns": columns,
        "file_id": file_id,
    }
