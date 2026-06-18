from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from data_analyst.api._common import ok, api_error
from data_analyst.config.settings import get_settings
from data_analyst.db.models import SessionRow, MessageRow
from data_analyst.db.session import get_session

router = APIRouter()


@router.get("")
def list_sessions(db: Session = Depends(get_session)):
    rows = (
        db.query(SessionRow)
        .order_by(SessionRow.last_active_at.desc())
        .all()
    )

    result = []
    for row in rows:
        total_tokens_in = (
            db.query(func.sum(MessageRow.tokens_input))
            .filter(MessageRow.session_id == row.id, MessageRow.role == "assistant")
            .scalar() or 0
        )
        total_tokens_out = (
            db.query(func.sum(MessageRow.tokens_output))
            .filter(MessageRow.session_id == row.id, MessageRow.role == "assistant")
            .scalar() or 0
        )
        msg_count = (
            db.query(func.count(MessageRow.id))
            .filter(MessageRow.session_id == row.id)
            .scalar() or 0
        )
        result.append({
            "session_id": row.id,
            "filename": row.filename,
            "status": row.status,
            "row_count": row.row_count,
            "column_names": json.loads(row.column_names),
            "message_count": msg_count,
            "total_tokens_input": total_tokens_in,
            "total_tokens_output": total_tokens_out,
            "created_at": row.created_at.isoformat(),
            "last_active_at": row.last_active_at.isoformat(),
        })
    return ok(result)


def _upload_dir(session_id: str) -> Path:
    path = Path(tempfile.gettempdir()) / "datachat" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("")
async def create_session(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
):
    settings = get_settings()

    contents = await file.read()
    if len(contents) > settings.max_upload_bytes:
        raise api_error(
            "FILE_TOO_LARGE",
            f"File exceeds maximum size of {settings.max_upload_bytes} bytes",
            status_code=413,
        )

    suffix = Path(file.filename or "data.csv").suffix.lower()
    if suffix not in (".csv", ".json"):
        raise api_error(
            "UNSUPPORTED_FORMAT",
            "Only CSV and JSON files are supported",
            status_code=422,
        )

    import pandas as pd

    session_id = str(uuid4())
    upload_path = _upload_dir(session_id) / (file.filename or "data")
    upload_path.write_bytes(contents)

    row = SessionRow(
        id=session_id,
        filename=file.filename or "upload",
        file_path=str(upload_path),
        file_size_bytes=len(contents),
    )
    db.add(row)
    db.flush()

    try:
        if suffix == ".csv":
            df = pd.read_csv(upload_path)
        else:
            df = pd.read_json(upload_path)
        row.row_count = len(df)
        row.column_names = json.dumps(list(df.columns))
        row.column_dtypes = json.dumps({col: str(dt) for col, dt in df.dtypes.items()})
        row.status = "ready"
    except Exception as exc:
        row.status = "error"
        row.error_message = str(exc)

    db.commit()

    return ok({
        "session_id": row.id,
        "filename": row.filename,
        "status": row.status,
        "row_count": row.row_count,
        "column_names": json.loads(row.column_names),
        "error_message": row.error_message,
    })


@router.get("/{session_id}")
def get_session_detail(session_id: str, db: Session = Depends(get_session)):
    row = db.get(SessionRow, session_id)
    if not row:
        raise api_error("SESSION_NOT_FOUND", "Session not found", status_code=404)

    return ok({
        "session_id": row.id,
        "filename": row.filename,
        "status": row.status,
        "row_count": row.row_count,
        "column_names": json.loads(row.column_names),
        "column_dtypes": json.loads(row.column_dtypes),
        "created_at": row.created_at.isoformat(),
        "last_active_at": row.last_active_at.isoformat(),
    })


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_session)):
    row = db.get(SessionRow, session_id)
    if not row:
        raise api_error("SESSION_NOT_FOUND", "Session not found", status_code=404)

    import shutil
    file_path = Path(row.file_path)
    if file_path.parent.exists():
        shutil.rmtree(str(file_path.parent), ignore_errors=True)

    db.delete(row)
    db.commit()
    return ok({"deleted": session_id})


@router.get("/{session_id}/messages")
def get_messages(session_id: str, db: Session = Depends(get_session)):
    row = db.get(SessionRow, session_id)
    if not row:
        raise api_error("SESSION_NOT_FOUND", "Session not found", status_code=404)

    messages = (
        db.query(MessageRow)
        .filter(MessageRow.session_id == session_id)
        .order_by(MessageRow.created_at)
        .all()
    )

    return ok([
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "reasoning_trace": m.get_reasoning_trace(),
            "iteration_count": m.iteration_count,
            "tokens_input": m.tokens_input,
            "tokens_output": m.tokens_output,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ])
