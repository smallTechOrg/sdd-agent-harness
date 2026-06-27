from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import api_error, ok
from datasets import build_profile, save_file
from db.models import DatasetRow
from db.session import get_session
from domain.dataset import DatasetResponse
from observability.events import get_logger

router = APIRouter()
log = get_logger("api.datasets")

# Generous Phase 1 caps — reasonable files only (a few thousand rows / a few MB).
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ROWS = 50_000

SUPPORTED_EXTENSIONS = {"csv"}


@router.post("/datasets")
def create_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    filename = file.filename or "upload"
    extension = Path(filename).suffix.lstrip(".").lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise api_error(
            "UNSUPPORTED_FORMAT",
            f"Unsupported file format '.{extension}'. Phase 1 accepts CSV only.",
            400,
        )

    # Read the raw bytes. This stays local — never sent to any external service.
    content = file.file.read()

    if len(content) > MAX_UPLOAD_BYTES:
        raise api_error(
            "FILE_TOO_LARGE",
            f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB Phase 1 limit.",
            413,
        )

    # Create the row first so save_file can key the local path off the dataset id.
    ds = DatasetRow(
        filename=filename,
        file_format=extension,
        local_path="",
        status="ready",
    )
    session.add(ds)
    session.flush()
    dataset_id = ds.id

    log.info(
        "dataset.upload_received",
        dataset_id=dataset_id,
        filename=filename,
        file_format=extension,
        bytes=len(content),
    )

    local_path = save_file(dataset_id, extension, content)

    try:
        profile = build_profile(local_path)
    except Exception as exc:  # noqa: BLE001 — surfaced as a structured 422
        log.info("dataset.parse_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error(
            "PARSE_FAILED",
            f"Could not parse the uploaded file as CSV: {exc}",
            422,
        )

    if profile.row_count > MAX_ROWS:
        raise api_error(
            "FILE_TOO_LARGE",
            f"File has {profile.row_count} rows, exceeding the Phase 1 cap of {MAX_ROWS}.",
            413,
        )

    ds.local_path = local_path
    ds.row_count = profile.row_count
    ds.column_count = profile.column_count
    ds.schema_summary = profile.schema_summary.model_dump_json()
    ds.status = "ready"

    log.info(
        "dataset.ready",
        dataset_id=dataset_id,
        row_count=profile.row_count,
        column_count=profile.column_count,
    )

    return ok(
        DatasetResponse(
            dataset_id=dataset_id,
            filename=filename,
            file_format=extension,
            row_count=profile.row_count,
            column_count=profile.column_count,
            columns=profile.columns,
            status="ready",
        ).model_dump()
    )


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: str,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(DatasetRow, dataset_id)
    if ds is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)

    import json

    columns: list[str] = []
    if ds.schema_summary:
        try:
            columns = [c["name"] for c in json.loads(ds.schema_summary).get("columns", [])]
        except (ValueError, KeyError, TypeError):
            columns = []

    return ok(
        DatasetResponse(
            dataset_id=ds.id,
            filename=ds.filename,
            file_format=ds.file_format,
            row_count=ds.row_count,
            column_count=ds.column_count,
            columns=columns,
            status=ds.status,
        ).model_dump()
    )
