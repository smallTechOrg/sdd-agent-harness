"""Dataset endpoints — upload + metadata fetch.

`POST /datasets` stores an uploaded CSV/xlsx locally, profiles it (schema +
row count) with NO LLM call, persists a Dataset row, and returns the id +
schema. `GET /datasets/{id}` re-reads that metadata. Raw rows never enter the
DB or any response — only schema + counts.
"""
import json

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import ok, api_error
from data.schema import infer
from data.storage import save_upload
from db.models import Dataset
from db.session import get_session
from domain.dataset import DatasetResponse

router = APIRouter()


def _dataset_to_wire(ds: Dataset) -> dict:
    """Build the spec/api.md `data` shape from a persisted Dataset row."""
    schema = json.loads(ds.schema_json)
    return DatasetResponse(
        dataset_id=ds.id,
        filename=ds.filename,
        file_type=ds.file_type,
        row_count=ds.row_count,
        schema={"columns": schema.get("columns", [])},
    ).to_wire()


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    if file is None or not file.filename:
        raise api_error("BAD_UPLOAD", "No file provided", 400)

    file_bytes = await file.read()

    # Storage + profiling validation errors surface as 400 BAD_UPLOAD:
    # unsupported type / empty / unreadable file all raise ValueError here.
    try:
        dataset_id, stored_path, file_type = save_upload(file_bytes, file.filename)
    except ValueError as exc:
        raise api_error("BAD_UPLOAD", str(exc), 400)

    try:
        schema = infer(stored_path)
    except ValueError as exc:
        raise api_error("BAD_UPLOAD", str(exc), 400)
    except Exception as exc:  # storage/profiling failure beyond bad input
        raise api_error("INTERNAL", f"Profiling failed: {exc}", 500)

    try:
        ds = Dataset(
            id=dataset_id,
            filename=file.filename,
            stored_path=stored_path,
            file_type=file_type,
            schema_json=json.dumps(schema),
            row_count=int(schema["row_count"]),
        )
        session.add(ds)
        session.flush()
        wire = _dataset_to_wire(ds)
    except Exception as exc:
        raise api_error("INTERNAL", f"Could not persist dataset: {exc}", 500)

    return ok(wire)


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    ds = session.get(Dataset, dataset_id)
    if ds is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)
    return ok(_dataset_to_wire(ds))
