"""POST /datasets — upload a CSV, ingest it into the local DuckDB working store,
profile its schema locally, and persist Dataset metadata.

Raw rows stay local (DuckDB / the uploaded file). Only schema + scalar
aggregates ever leave this machine. This route never returns raw rows.
"""

from __future__ import annotations

import json
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import ok, api_error
from config.settings import get_settings
from db.models import DatasetRow
from db.session import get_session
from domain.dataset import ColumnInfo, DatasetResponse
from tools.duckdb_store import load_csv
from tools.profile import build_schema_summary

router = APIRouter()


def _looks_like_csv(upload: UploadFile) -> bool:
    name = (upload.filename or "").lower()
    content_type = (upload.content_type or "").lower()
    return name.endswith(".csv") or content_type in (
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
    )


@router.post("/datasets")
def create_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    if not _looks_like_csv(file):
        raise api_error("BAD_UPLOAD", "Couldn't read that file — please upload a CSV.", 400)

    dataset_id = str(uuid4())
    original_name = file.filename or f"{dataset_id}.csv"

    upload_dir = get_settings().upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    saved_path = os.path.join(upload_dir, f"{dataset_id}.csv")

    # Persist the uploaded bytes locally before ingestion.
    try:
        contents = file.file.read()
        with open(saved_path, "wb") as out:
            out.write(contents)
    except Exception as exc:  # noqa: BLE001
        raise api_error("COMPUTE_FAILED", f"Couldn't save the uploaded file: {exc}", 500)

    # Ingest into the local DuckDB working store.
    try:
        row_count = load_csv(saved_path, dataset_id)
    except (ValueError, FileNotFoundError) as exc:
        # Unparseable / malformed CSV is a bad upload, not a server fault.
        raise api_error("BAD_UPLOAD", f"Couldn't read that CSV: {exc}", 400)
    except Exception as exc:  # noqa: BLE001
        raise api_error("COMPUTE_FAILED", f"Local ingestion failed: {exc}", 500)

    # Profile the schema locally (schema + scalar aggregates only — no rows).
    try:
        schema_summary = build_schema_summary(dataset_id)
    except Exception as exc:  # noqa: BLE001
        raise api_error("COMPUTE_FAILED", f"Schema profiling failed: {exc}", 500)

    dataset = DatasetRow(
        id=dataset_id,
        name=original_name,
        source_type="csv",
        row_count=row_count,
        schema_summary=json.dumps(schema_summary),
    )
    session.add(dataset)

    response = DatasetResponse(
        dataset_id=dataset_id,
        name=original_name,
        row_count=row_count,
        columns=[
            ColumnInfo(name=c["name"], type=c["type"])
            for c in schema_summary["columns"]
        ],
    )
    return ok(response.model_dump())
