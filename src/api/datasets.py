"""DataChat HTTP surface — the integration router.

Wires the finished slices behind ``spec/api.md`` (the contract):

  POST /api/datasets                       upload + local profile (no LLM)
  POST /api/datasets/{dataset_id}/ask      analyze, streamed back via SSE
  GET  /api/datasets/{dataset_id}          load a dataset + its thread
  GET  /api/datasets/{dataset_id}/messages run-history summaries
  GET  /api/messages/{message_id}          full run record
  GET  /api/datasets                       library list (Phase 1 STUB → real in Phase 3)

Every JSON route returns the skeleton envelope ``ok(data)`` or raises
``api_error(code, message, status)``. The analyze route streams a
``text/event-stream`` whose failure rides the stream as an ``error`` event — it
does NOT 500 mid-stream (only the pre-stream unknown-dataset / empty-question
checks raise).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi import File as FastAPIFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse

from api._common import api_error, ok
from config.settings import get_settings
from db.models import DatasetRow, MessageRow
from db.session import get_session
from execution.profile import MalformedCSVError, profile_csv
from graph.runner import DatasetNotFoundError, stream_analysis

router = APIRouter(prefix="/api")
log = structlog.get_logger(__name__)

# Uploaded files live on local disk (never in the DB) — data/uploads/<id>.csv.
# __file__ = src/api/datasets.py → 2 parents up = src/, 3 = repo root.
_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"

_CHUNK = 1024 * 1024  # 1 MiB streaming write chunk


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #

class AskRequest(BaseModel):
    question: str = ""


# --------------------------------------------------------------------------- #
# JSON serialization helpers (parse the row's JSON columns out to dicts)
# --------------------------------------------------------------------------- #

def _loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _profile_of(row: DatasetRow) -> dict[str, Any]:
    parsed = _loads(row.profile_json)
    return parsed if isinstance(parsed, dict) else {}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _message_thread_entry(msg: MessageRow) -> dict[str, Any]:
    """The conversation/thread view of a message (GET /datasets/{id})."""
    return {
        "id": msg.id,
        "question": msg.question,
        "answer": msg.answer,
        "status": msg.status,
        "key_numbers": _loads(msg.key_numbers_json) or {},
        "result_table": _loads(msg.result_table_json),
        "cost_usd": msg.cost_usd,
        "created_at": _iso(msg.created_at),
    }


def _message_summary(msg: MessageRow) -> dict[str, Any]:
    """The history-list view of a message (GET /datasets/{id}/messages)."""
    return {
        "id": msg.id,
        "question": msg.question,
        "status": msg.status,
        "cost_usd": msg.cost_usd,
        "created_at": _iso(msg.created_at),
    }


def _message_detail(msg: MessageRow) -> dict[str, Any]:
    """The full run record (GET /messages/{id})."""
    return {
        "id": msg.id,
        "dataset_id": msg.dataset_id,
        "question": msg.question,
        "plan": msg.plan,
        "generated_code": msg.generated_code,
        "answer": msg.answer,
        "key_numbers": _loads(msg.key_numbers_json) or {},
        "result_table": _loads(msg.result_table_json),
        "prompt_tokens": msg.prompt_tokens,
        "completion_tokens": msg.completion_tokens,
        "cost_usd": msg.cost_usd,
        "status": msg.status,
        "error": msg.error,
        "created_at": _iso(msg.created_at),
        "completed_at": _iso(msg.completed_at),
    }


# --------------------------------------------------------------------------- #
# POST /api/datasets — upload + profile (REAL, no LLM)
# --------------------------------------------------------------------------- #

@router.post("/datasets")
def upload_dataset(
    file: UploadFile = FastAPIFile(...),
    session: Session = Depends(get_session),
) -> dict:
    """Upload one CSV, store it locally, profile it with pandas (no LLM)."""
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise api_error(
            "UNSUPPORTED_TYPE",
            "Only .csv files are supported. Excel/multi-sheet — coming in a later phase.",
            400,
        )

    max_bytes = int(get_settings().max_upload_mb) * 1024 * 1024
    dataset_id = str(uuid.uuid4())
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = _UPLOAD_DIR / f"{dataset_id}.csv"

    # Stream the upload to disk, enforcing the size cap as we go so an oversized
    # file is rejected without buffering it all in memory.
    written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = file.file.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    _safe_unlink(dest)
                    raise api_error(
                        "FILE_TOO_LARGE",
                        f"File exceeds the {get_settings().max_upload_mb} MB upload limit.",
                        413,
                    )
                out.write(chunk)
    except HTTPException:  # FILE_TOO_LARGE — re-raise as-is (already cleaned up)
        raise
    except Exception as exc:  # noqa: BLE001 — disk write failure
        _safe_unlink(dest)
        log.error("upload_write_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error("UPLOAD_FAILED", f"Could not store the uploaded file: {exc}", 500)

    if written == 0:
        _safe_unlink(dest)
        raise api_error("MALFORMED_FILE", "The uploaded file is empty.", 400)

    # Profile locally (pure pandas, NO LLM). Malformed → 400 + clean up the file.
    try:
        profile = profile_csv(str(dest), get_settings().sample_rows)
    except MalformedCSVError as exc:
        _safe_unlink(dest)
        raise api_error("MALFORMED_FILE", f"Could not parse the CSV: {exc}", 400)
    except Exception as exc:  # noqa: BLE001 — unexpected profiling failure
        _safe_unlink(dest)
        log.error("profile_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error("MALFORMED_FILE", f"Could not profile the CSV: {exc}", 400)

    name = os.path.basename(filename)
    row = DatasetRow(
        id=dataset_id,
        name=name,
        original_filename=name,
        file_path=str(dest),
        profile_json=json.dumps(profile),
        source_kind="csv",
    )
    session.add(row)
    session.flush()

    log.info(
        "dataset_uploaded",
        dataset_id=dataset_id,
        name=name,
        row_count=profile.get("row_count"),
        bytes=written,
    )
    return ok({"dataset_id": dataset_id, "name": name, "profile": profile})


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:  # pragma: no cover — best-effort cleanup
        pass


# --------------------------------------------------------------------------- #
# POST /api/datasets/{dataset_id}/ask — analyze (REAL, streaming SSE)
# --------------------------------------------------------------------------- #

def _sse(events: Iterator[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Map runner ``{"event","data"}`` dicts into sse-starlette frames.

    Each yielded dict becomes one SSE frame: ``event: <name>`` + ``data: <json>``.
    JSON-encode the payload here (sse-starlette emits ``data`` verbatim). Yielding
    one item per event keeps tokens flushing live — nothing is buffered.
    """
    for ev in events:
        yield {
            "event": ev.get("event", "message"),
            "data": json.dumps(ev.get("data", {})),
        }


@router.post("/datasets/{dataset_id}/ask")
def ask(
    dataset_id: str,
    req: AskRequest,
    session: Session = Depends(get_session),
):
    """Ask a question; stream the agent's answer back via SSE.

    Pre-stream errors raise (400 EMPTY_QUESTION / 404 NOT_FOUND). Once the
    stream starts, an analysis failure rides it as an ``error`` event — the
    server never 500s mid-stream.
    """
    question = (req.question or "").strip()
    if not question:
        raise api_error("EMPTY_QUESTION", "The question must not be blank.", 400)

    # Confirm the dataset exists BEFORE returning the stream → 404 NOT_FOUND.
    if session.get(DatasetRow, dataset_id) is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)

    log.info("ask_received", dataset_id=dataset_id, question=question[:120])
    # stream_analysis re-checks the dataset and may raise DatasetNotFoundError
    # before yielding — guard the generator so that, too, surfaces as 404.
    try:
        gen = stream_analysis(dataset_id, question)
    except DatasetNotFoundError:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)

    return EventSourceResponse(_sse(gen))


# --------------------------------------------------------------------------- #
# GET /api/datasets/{dataset_id} — dataset + its thread (REAL)
# --------------------------------------------------------------------------- #

@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)

    messages = (
        session.query(MessageRow)
        .filter(MessageRow.dataset_id == dataset_id)
        .order_by(MessageRow.created_at.asc())
        .all()
    )
    return ok(
        {
            "dataset_id": row.id,
            "name": row.name,
            "profile": _profile_of(row),
            "messages": [_message_thread_entry(m) for m in messages],
        }
    )


# --------------------------------------------------------------------------- #
# GET /api/datasets/{dataset_id}/messages — run-history summaries (REAL)
# --------------------------------------------------------------------------- #

@router.get("/datasets/{dataset_id}/messages")
def list_messages(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    if session.get(DatasetRow, dataset_id) is None:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found.", 404)
    messages = (
        session.query(MessageRow)
        .filter(MessageRow.dataset_id == dataset_id)
        .order_by(MessageRow.created_at.asc())
        .all()
    )
    return ok([_message_summary(m) for m in messages])


# --------------------------------------------------------------------------- #
# GET /api/messages/{message_id} — full run record (REAL)
# --------------------------------------------------------------------------- #

@router.get("/messages/{message_id}")
def get_message(message_id: str, session: Session = Depends(get_session)) -> dict:
    msg = session.get(MessageRow, message_id)
    if msg is None:
        raise api_error("NOT_FOUND", f"Message {message_id} not found.", 404)
    return ok(_message_detail(msg))


# --------------------------------------------------------------------------- #
# GET /api/datasets — library list (Phase 1 STUB; real from Phase 3)
# --------------------------------------------------------------------------- #

@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    """STUB (Phase 1): the persistent multi-dataset library is Phase 3.

    Returns the active datasets as summaries so the route is real and returns
    the envelope, but the persistent-library UX (reopen across days, derived
    items) is deferred. The frontend labels the sidebar as a stub.
    """
    rows = (
        session.query(DatasetRow)
        .order_by(DatasetRow.created_at.desc())
        .all()
    )
    return ok(
        [
            {
                "dataset_id": r.id,
                "name": r.name,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]
    )
