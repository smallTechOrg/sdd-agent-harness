"""Dataset upload + ask endpoints (Phase 1 core contract)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import DatasetRow
from domain.analysis import AskRequest
from analysis.ingest import ingest_csv, IngestError, FileTooLargeError
from analysis.profiler import profile_dataset
from graph.runner import run_analysis, DatasetNotFound
from observability.events import get_logger

router = APIRouter()
log = get_logger("api")


@router.post("/datasets")
async def create_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise api_error("BAD_FILE", "Only CSV files are supported.", 400)

    content = await file.read()

    try:
        ingested = ingest_csv(filename, content)
    except FileTooLargeError as exc:
        raise api_error("FILE_TOO_LARGE", str(exc), 413)
    except IngestError as exc:
        raise api_error("BAD_FILE", str(exc), 400)
    except Exception as exc:  # unexpected DuckDB/IO failure
        log.error("ingest.failed", filename=filename, error=str(exc))
        raise api_error("INGEST_FAILED", f"Ingest failed: {exc}", 500)

    # Auto-profile in DuckDB (aggregate stats only — no raw rows leave DuckDB).
    # Non-fatal: a profiling failure must not block the upload.
    try:
        profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    except Exception as exc:  # defensive — profiling never blocks ingest
        log.warning("profile.failed", filename=filename, error=str(exc))
        profile = []

    dataset = DatasetRow(
        name=filename,
        duckdb_path=ingested["duckdb_path"],
        table_name=ingested["table_name"],
        schema_json=json.dumps(ingested["schema"]),
        row_count=ingested["row_count"],
        profile_json=json.dumps(profile) if profile else None,
    )
    session.add(dataset)
    session.flush()
    dataset_id = dataset.id

    log.info(
        "ingest.ok",
        dataset_id=dataset_id,
        name=filename,
        row_count=ingested["row_count"],
        column_count=len(ingested["schema"]),
        profiled_columns=len(profile),
    )

    return ok(
        {
            "id": dataset_id,
            "name": filename,
            "row_count": ingested["row_count"],
            "schema": ingested["schema"],
            "profile": profile or None,
        }
    )


@router.post("/datasets/{dataset_id}/ask")
def ask(
    dataset_id: str,
    req: AskRequest,
    session: Session = Depends(get_session),
) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise api_error("EMPTY_QUESTION", "Question must not be empty.", 400)

    try:
        result = run_analysis(dataset_id, question)
    except DatasetNotFound:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)

    # Always include the null placeholders so the frontend can wire stub panels.
    return ok(
        {
            "run_id": result["run_id"],
            "dataset_id": result["dataset_id"],
            "status": result["status"],
            "question": result["question"],
            "answer": result["answer"],
            "sql": result["sql"],
            "result": result["result"],
            "flagged": result["flagged"],
            "error": result["error"],
            "chart": result["chart"],
            "summary_table": result["summary_table"],
            "followups": result["followups"],
            "tokens": None,  # Phase 3.
        }
    )
