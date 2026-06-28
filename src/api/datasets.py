"""Datasets API router (see spec/api.md).

POST /datasets               — upload a CSV, ingest into local DuckDB, profile (no LLM).
GET  /datasets               — list datasets newest-first for the sidebar (no LLM).
GET  /datasets/{id}          — re-fetch the profile.
GET  /datasets/{id}/runs     — question/run history newest-first (no LLM — pure DB read).
POST /datasets/{id}/ask      — run the agent; answer + chart + table + trace.
"""
from fastapi import APIRouter, File, UploadFile

from api._common import api_error, ok
from domain.dataset import AskRequest
from graph.runner import (
    get_dataset_payload,
    get_dataset_runs,
    ingest_dataset,
    list_datasets,
    run_question,
)

router = APIRouter()

# ~100MB upload cap.
_MAX_BYTES = 100 * 1024 * 1024


@router.post("/datasets")
async def create_dataset(file: UploadFile = File(...)) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise api_error("BAD_FILE", "Only .csv files are supported in Phase 1.", 400)

    contents = await file.read()
    if not contents:
        raise api_error("BAD_FILE", "Uploaded file is empty.", 400)
    if len(contents) > _MAX_BYTES:
        raise api_error(
            "FILE_TOO_LARGE", "File exceeds the 100MB limit.", 413
        )

    try:
        payload = ingest_dataset(filename, contents)
    except Exception as exc:  # DuckDB ingest / profile failure
        raise api_error("INGEST_FAILED", f"Could not ingest CSV: {exc}", 500)

    return ok(payload)


@router.get("/datasets")
def list_all_datasets() -> dict:
    """List datasets newest-first for the sidebar. Pure DB read — no LLM."""
    return ok(list_datasets())


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str) -> dict:
    payload = get_dataset_payload(dataset_id)
    if payload is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)
    return ok(payload)


@router.get("/datasets/{dataset_id}/runs")
def get_runs(dataset_id: str) -> dict:
    """Question/run history newest-first. Pure DB read — no LLM, no DuckDB.

    Each record reconstructs the live ``AskResult`` shape from the persisted
    bounded record so a re-opened run renders identically to a live ask.
    """
    runs = get_dataset_runs(dataset_id)
    if runs is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)
    return ok(runs)


@router.post("/datasets/{dataset_id}/ask")
def ask_dataset(dataset_id: str, req: AskRequest) -> dict:
    if not req.question or not req.question.strip():
        raise api_error("EMPTY_QUESTION", "Question must not be blank.", 422)

    payload = run_question(dataset_id, req.question.strip())
    if payload is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)
    # Agent failure is reported in the body with HTTP 200 (status="failed").
    return ok(payload)
