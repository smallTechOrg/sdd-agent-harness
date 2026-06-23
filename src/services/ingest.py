"""Upload ingestion orchestration (pure service — no FastAPI here).

Reads a CSV/XLSX upload into pandas, materialises a typed table in DuckDB,
profiles its schema, captures a token-economy-capped sample preview, and records
a ``DatasetRow`` in the metadata store linked to the active session.
"""
from __future__ import annotations

import io
import json
import os

import pandas as pd
from sqlalchemy.orm import Session

from db.models import DatasetRow, SessionRow
from services import duckdb_store

DEFAULT_SESSION_NAME = "Default session"


def _json_safe(value):
    """Coerce a pandas/numpy scalar into a JSON-serialisable Python value."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, bool, int, float)):
        return value
    # numpy scalars expose .item(); fall back to str for everything else.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def get_or_create_default_session(db_session: Session) -> SessionRow:
    """Return the default :class:`SessionRow`, creating it if absent."""
    existing = (
        db_session.query(SessionRow)
        .filter(SessionRow.name == DEFAULT_SESSION_NAME)
        .order_by(SessionRow.created_at.asc())
        .first()
    )
    if existing is not None:
        return existing
    session_row = SessionRow(name=DEFAULT_SESSION_NAME)
    db_session.add(session_row)
    db_session.flush()  # populate id without committing the caller's txn
    return session_row


def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename or "")[1].lower()
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")
    try:
        if ext == ".csv":
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        else:
            raise ValueError(
                f"Unsupported file type '{ext or filename}'. "
                "Upload a .csv or .xlsx file."
            )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - parse errors map to 400 upstream
        raise ValueError(f"Could not parse '{filename}': {exc}") from exc

    if df is None or df.shape[1] == 0:
        raise ValueError(f"Dataset '{filename}' has no columns.")
    if df.shape[0] == 0:
        raise ValueError(f"Dataset '{filename}' contains no rows.")
    return df


def ingest_file(
    file_bytes: bytes,
    filename: str,
    session_id: str | None,
    duckdb_path: str,
    max_sample_rows: int,
    db_session: Session,
) -> DatasetRow:
    """Ingest an uploaded CSV/XLSX file and return the persisted ``DatasetRow``.

    Raises ``ValueError`` for unsupported type / unparseable / empty datasets
    (these map to HTTP 400 upstream). The ``DatasetRow`` is added and flushed so
    its ``id`` is available; the caller owns the commit.
    """
    df = _read_dataframe(file_bytes, filename)

    # Resolve the owning session (explicit id, else the default session).
    if session_id:
        session_row = db_session.get(SessionRow, session_id)
        if session_row is None:
            raise ValueError(f"Session '{session_id}' does not exist.")
    else:
        session_row = get_or_create_default_session(db_session)

    table_name = duckdb_store.sanitize_table_name(filename)
    row_count = duckdb_store.ingest_dataframe(df, table_name, duckdb_path)

    schema = duckdb_store.get_schema(table_name, duckdb_path)
    cap = max(0, int(max_sample_rows))
    raw_samples = duckdb_store.get_sample_rows(table_name, duckdb_path, cap)
    # Token-economy: never store/expose more than the cap.
    sample_rows = [[_json_safe(v) for v in row] for row in raw_samples[:cap]]

    name = os.path.splitext(os.path.basename(filename or "dataset"))[0] or "dataset"

    dataset = DatasetRow(
        session_id=session_row.id,
        name=name,
        source_filename=filename,
        duckdb_table=table_name,
        row_count=row_count,
        schema_json=json.dumps(schema),
        sample_rows_json=json.dumps(sample_rows),
    )
    db_session.add(dataset)
    db_session.flush()
    return dataset
