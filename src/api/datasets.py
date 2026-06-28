"""Dataset routes: upload + profile, and fetch-by-id.

``POST /datasets`` is the upload seam: store the raw file, convert to Parquet,
profile the FULL dataframe, ask Gemini for 2-3 suggestions, persist a
``datasets`` row, and return the profile. ``GET /datasets/{id}`` reads it back.

Every external/DB call is wrapped so a missing key or provider error surfaces as
a structured ``api_error`` — never a 500 stacktrace to the user. ``save_upload``
raises ``ValueError`` on a parse failure, which maps to 422 ``PARSE_ERROR`` with
nothing persisted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import api_error, ok
from api.schemas import DatasetResponse
from db.models import Dataset
from db.session import get_session
from datasets.store import load_dataframe, save_upload
from datasets.profiler import profile_dataframe, suggest_questions

router = APIRouter()

_DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # ~100MB
_ALLOWED_EXTS = {".csv", ".xlsx"}


def _max_upload_bytes() -> int:
    """Read ``AGENT_MAX_UPLOAD_BYTES`` defensively (settings slice owns the model)."""
    try:
        from config.settings import get_settings

        val = getattr(get_settings(), "max_upload_bytes", None)
        if val:
            return int(val)
    except Exception:
        pass
    raw = os.environ.get("AGENT_MAX_UPLOAD_BYTES")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_MAX_UPLOAD_BYTES


def _parsed_profile(row: Dataset) -> dict:
    if not row.profile_json:
        return {}
    try:
        return json.loads(row.profile_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parsed_suggestions(row: Dataset) -> list[str]:
    if not row.suggested_questions_json:
        return []
    try:
        data = json.loads(row.suggested_questions_json)
        if isinstance(data, list):
            return [str(q) for q in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


@router.post("/datasets")
async def upload_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise api_error(
            "PARSE_ERROR",
            f"Unsupported file type '{ext or '(none)'}'. Upload a .csv or .xlsx file.",
            422,
        )

    file_bytes = await file.read()
    limit = _max_upload_bytes()
    if len(file_bytes) > limit:
        raise api_error(
            "FILE_TOO_LARGE",
            f"File is {len(file_bytes)} bytes, over the {limit}-byte limit.",
            413,
        )

    dataset_id = str(uuid4())

    # Store + convert to Parquet. A parse failure is a clean 422 with nothing persisted.
    try:
        stored = save_upload(file_bytes, filename, dataset_id)
    except ValueError as exc:
        raise api_error("PARSE_ERROR", str(exc), 422)
    except Exception as exc:  # pragma: no cover - unexpected disk/IO error
        raise api_error("STORAGE_ERROR", f"Could not store the upload: {exc}", 500)

    # Profile the FULL dataframe; suggestions degrade gracefully if the LLM is down.
    try:
        df = load_dataframe(stored["parquet_path"])
        profile = profile_dataframe(df)
    except Exception as exc:
        raise api_error("PROFILE_ERROR", f"Could not profile the dataset: {exc}", 500)

    try:
        suggestions = suggest_questions(profile)
    except Exception:
        # never crash the upload on the suggestion step
        suggestions = []

    # Persist ABSOLUTE on-disk paths: the sandbox subprocess runs with a changed
    # cwd, so a relative parquet path would not resolve when it loads the data.
    parquet_path = str(Path(stored["parquet_path"]).resolve())
    upload_path = str(Path(stored["upload_path"]).resolve())

    row = Dataset(
        id=dataset_id,
        filename=filename,
        row_count=stored["row_count"],
        column_count=stored["column_count"],
        profile_json=json.dumps(profile, default=str),
        suggested_questions_json=json.dumps(suggestions),
        parquet_path=parquet_path,
        upload_path=upload_path,
        status="ready",
    )
    session.add(row)
    session.flush()

    return ok(
        DatasetResponse(
            dataset_id=dataset_id,
            filename=filename,
            row_count=stored["row_count"],
            column_count=stored["column_count"],
            profile=profile,
            suggested_questions=suggestions,
            status="ready",
        ).model_dump()
    )


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(Dataset, dataset_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)

    return ok(
        DatasetResponse(
            dataset_id=row.id,
            filename=row.filename,
            row_count=row.row_count,
            column_count=row.column_count,
            profile=_parsed_profile(row),
            suggested_questions=_parsed_suggestions(row),
            status=row.status,
        ).model_dump()
    )
