"""Dataset upload + listing endpoints (spec/api.md)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session

router = APIRouter()


def _schema_list(dataset) -> list[dict]:
    raw = getattr(dataset, "schema_json", None)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    out = []
    for item in parsed:
        if isinstance(item, dict):
            out.append({"name": item.get("name"), "type": item.get("type")})
    return out


def _sample_rows(dataset) -> list[list]:
    raw = getattr(dataset, "sample_rows_json", None)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def _dataset_out(dataset) -> dict:
    created = getattr(dataset, "created_at", None)
    return {
        "id": dataset.id,
        "name": dataset.name,
        "session_id": getattr(dataset, "session_id", None),
        "row_count": dataset.row_count,
        "schema": _schema_list(dataset),
        "sample_rows": _sample_rows(dataset),
        "created_at": created.isoformat() if created is not None else None,
    }


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    db: Session = Depends(get_session),
) -> dict:
    from config.settings import get_settings
    from services import ingest as ingest_svc

    settings = get_settings()

    file_bytes = await file.read()
    if not file_bytes:
        raise api_error("BAD_REQUEST", "Uploaded file is empty", 400)

    filename = file.filename or "upload"

    # Resolve / create the session.
    resolved_session_id = session_id
    if not resolved_session_id:
        get_default = getattr(ingest_svc, "get_or_create_default_session", None)
        if callable(get_default):
            sess = get_default(db)
            resolved_session_id = getattr(sess, "id", None) or (
                sess.get("id") if isinstance(sess, dict) else None
            )

    try:
        dataset = ingest_svc.ingest_file(
            file_bytes=file_bytes,
            filename=filename,
            session_id=resolved_session_id,
            duckdb_path=settings.duckdb_path,
            max_sample_rows=int(settings.max_sample_rows),
            db_session=db,
        )
    except ValueError as exc:
        raise api_error("BAD_REQUEST", str(exc), 400)
    except Exception as exc:  # noqa: BLE001 - ingestion / DuckDB failure
        raise api_error("INGEST_FAILED", f"Ingestion failed: {exc}", 500)

    return ok(_dataset_out(dataset))


@router.get("/datasets")
def list_datasets(
    session_id: str | None = None,
    db: Session = Depends(get_session),
) -> dict:
    from db.models import DatasetRow
    from services import ingest as ingest_svc

    resolved_session_id = session_id
    if not resolved_session_id:
        get_default = getattr(ingest_svc, "get_or_create_default_session", None)
        if callable(get_default):
            sess = get_default(db)
            resolved_session_id = getattr(sess, "id", None) or (
                sess.get("id") if isinstance(sess, dict) else None
            )

    q = db.query(DatasetRow)
    if resolved_session_id:
        q = q.filter(DatasetRow.session_id == resolved_session_id)
    rows = q.order_by(DatasetRow.created_at.desc()).all()
    return ok([_dataset_out(r) for r in rows])
