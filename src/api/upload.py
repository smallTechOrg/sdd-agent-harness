"""`POST /upload` — register an uploaded data file as a dataset (Phase 2).

Parses the file with pandas by extension, computes a sha256 of the raw bytes,
duplicate-checks against existing `datasets` rows (C10), persists a CSV + Parquet
copy under `uploads/`, and creates a `DatasetRow` (origin=uploaded). The async
auto-notes trigger (C30) is Phase 4 — `auto_notes_status` is left `None` here.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import DatasetRow
from db.session import get_session
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.upload")

# repo root = src/api/upload.py -> 3 parents up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOADS_DIR = _REPO_ROOT / "uploads"

# extension -> (format label, pandas reader)
_EXT_TO_FORMAT = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".txt": "txt",
    ".json": "json",
    ".xlsx": "excel",
    ".xls": "excel",
}


def _ensure_uploads_dir() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _parse_dataframe(raw: bytes, ext: str) -> pd.DataFrame:
    """Parse raw bytes into a DataFrame by extension. Raises ValueError on failure."""
    buf = io.BytesIO(raw)
    if ext == ".csv":
        return pd.read_csv(buf)
    if ext in (".tsv", ".txt"):
        return pd.read_csv(buf, sep="\t")
    if ext == ".json":
        return pd.read_json(buf)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(buf)
    raise ValueError(f"Unsupported extension: {ext}")


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    context: str | None = Form(default=None),
    notes_file: UploadFile | None = File(default=None),
    force: bool = False,
    session: Session = Depends(get_session),
) -> dict:
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    fmt = _EXT_TO_FORMAT.get(ext)
    if fmt is None:
        raise api_error(
            "bad_extension",
            f"Unsupported file type {ext!r}. Accepted: .csv .tsv .txt .json .xlsx .xls",
            400,
        )

    raw = await file.read()
    if not raw or not raw.strip():
        raise api_error("empty_file", "Uploaded file is empty.", 400)

    content_hash = hashlib.sha256(raw).hexdigest()

    # Parse with pandas; an unparseable / empty-table file is a 400.
    try:
        df = _parse_dataframe(raw, ext)
    except Exception as exc:  # pandas raises many shapes; treat all as unparseable
        raise api_error("unparseable_file", f"Could not parse file: {exc}", 400)

    if df.shape[0] == 0 or df.shape[1] == 0:
        raise api_error("empty_file", "Uploaded file has no data rows/columns.", 400)

    # Duplicate check (C10): same content hash AND same filename -> 409 unless force.
    if not force:
        existing = session.execute(
            select(DatasetRow).where(DatasetRow.content_hash == content_hash)
        ).scalars().all()
        for row in existing:
            same_name = row.filename == filename
            match_type = "content_and_name" if same_name else "content"
            # Duplicate carries extra resolution fields beyond {code,message};
            # build the HTTPException directly to keep the same `detail` envelope.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_dataset",
                    "message": "This file was already uploaded. Re-upload with force=true to keep both.",
                    "match_type": match_type,
                    "existing_dataset_id": row.id,
                    "existing_filename": row.filename,
                },
            )

    columns = [str(c) for c in df.columns]
    columns_json = [
        {"name": str(c), "dtype": str(df[c].dtype)} for c in df.columns
    ]

    # Create the row first to get its id (drives the on-disk filenames).
    row = DatasetRow(
        filename=filename,
        file_path="",  # set below once id is known
        row_count=int(df.shape[0]),
        col_count=int(df.shape[1]),
        columns_json=columns_json,
        content_hash=content_hash,
        format=fmt,
        context=context,
        origin="uploaded",
        auto_notes_status=None,  # Phase 4 triggers C30; Phase 2 leaves it null
    )
    session.add(row)
    session.flush()  # assigns row.id
    dataset_id = row.id

    csv_path = UPLOADS_DIR / f"{dataset_id}.csv"
    parquet_path = UPLOADS_DIR / f"{dataset_id}.parquet"
    try:
        _ensure_uploads_dir()
        df.to_csv(csv_path, index=False)
        df.to_parquet(parquet_path, index=False)
    except Exception as exc:
        logger.error("upload_write_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error("write_failed", f"Failed to write dataset to disk: {exc}", 500)

    row.file_path = str(csv_path)
    row.parquet_path = str(parquet_path)

    logger.info("upload_ok", dataset_id=dataset_id, rows=row.row_count, cols=row.col_count)

    return ok(
        {
            "dataset_id": dataset_id,
            "filename": filename,
            "format": fmt,
            "row_count": row.row_count,
            "col_count": row.col_count,
            "columns": columns,
            "context": context,
            "auto_notes_status": None,
        }
    )
