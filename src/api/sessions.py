"""Sessions API router: file upload, file listing, analysis."""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session, create_db_session
from db.models import SessionRow, UploadedFileRow
from domain.session import (
    AnalyzeRequest,
    AnalyzeResponse,
    FileUploadResponse,
    SessionResponse,
    UploadedFileInfo,
)
from db.models import RunRow

router = APIRouter()
log = structlog.get_logger(__name__)

_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/sessions")
def create_session(session: Session = Depends(get_session)) -> dict:
    """Create a new analysis session."""
    row = SessionRow()
    session.add(row)
    session.flush()
    session_id = row.id
    created_at = row.created_at.isoformat() if row.created_at else None
    log.info("session_created", session_id=session_id)
    return ok(SessionResponse(session_id=session_id, created_at=created_at).model_dump())


@router.post("/sessions/{session_id}/files")
async def upload_file(
    session_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    """Upload a CSV or Excel file for a session."""
    # Verify session exists
    sess_row = session.get(SessionRow, session_id)
    if sess_row is None:
        raise api_error("session_not_found", f"Session {session_id} not found", 404)

    # Read file bytes
    file_bytes = await file.read()

    # Check file size
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise api_error("file_too_large", "File exceeds 50 MB limit", 413)

    filename = file.filename or "upload.csv"

    # Check extension
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"csv", "xlsx", "xls"}:
        raise api_error(
            "unsupported_format",
            f"Unsupported file format: .{suffix}. Must be .csv, .xlsx, or .xls",
            422,
        )

    # Get the engine from the session
    from db.session import _get_engine
    engine = _get_engine()

    # Ingest the file
    try:
        from ingest.file_ingest import ingest_file
        result = ingest_file(file_bytes, filename, session_id, engine)
    except ValueError as exc:
        err_msg = str(exc)
        if "format" in err_msg.lower():
            raise api_error("unsupported_format", err_msg, 422)
        elif "row" in err_msg.lower() or "500,000" in err_msg or "500000" in err_msg:
            raise api_error("too_many_rows", err_msg, 422)
        elif "parse" in err_msg.lower() or "failed to parse" in err_msg.lower():
            raise api_error("parse_failed", err_msg, 422)
        else:
            raise api_error("parse_failed", err_msg, 422)
    except RuntimeError as exc:
        raise api_error("ingest_failed", str(exc), 500)

    return ok(FileUploadResponse(
        table_name=result["table_name"],
        row_count=result["row_count"],
        columns=result["columns"],
        file_id=result.get("file_id"),
    ).model_dump())


@router.get("/sessions/{session_id}/files")
def list_files(
    session_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """List all uploaded files for a session."""
    sess_row = session.get(SessionRow, session_id)
    if sess_row is None:
        raise api_error("session_not_found", f"Session {session_id} not found", 404)

    file_rows = (
        session.query(UploadedFileRow)
        .filter(UploadedFileRow.session_id == session_id)
        .order_by(UploadedFileRow.created_at)
        .all()
    )

    files = [
        UploadedFileInfo(
            file_id=r.id,
            filename=r.filename,
            table_name=r.table_name,
            row_count=r.row_count,
            columns=json.loads(r.column_names),
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in file_rows
    ]

    return ok({"files": [f.model_dump() for f in files]})


@router.post("/sessions/{session_id}/analyze")
def analyze(
    session_id: str,
    req: AnalyzeRequest,
    session: Session = Depends(get_session),
) -> dict:
    """Run the analysis graph for a natural-language question."""
    # Verify session exists
    sess_row = session.get(SessionRow, session_id)
    if sess_row is None:
        raise api_error("session_not_found", f"Session {session_id} not found", 404)

    # Validate question
    if not req.question or not req.question.strip():
        raise api_error("validation_error", "question must not be empty", 422)

    # Check files uploaded
    file_count = (
        session.query(UploadedFileRow)
        .filter(UploadedFileRow.session_id == session_id)
        .count()
    )
    if file_count == 0:
        raise api_error("no_tables", "No files have been uploaded to this session", 422)

    # Run agent graph
    from graph.runner import run_agent
    run_id = run_agent(session_id=session_id, question=req.question)

    # Fetch run result
    with create_db_session() as db_session:
        run = db_session.get(RunRow, run_id)
        if run is None:
            raise api_error("run_not_found", "Run not found after creation", 500)

        # Parse JSON fields
        insight_json = None
        if run.insight_json:
            try:
                insight_json = json.loads(run.insight_json)
            except Exception:
                insight_json = None

        chart_specs = None
        if run.chart_specs:
            try:
                chart_specs = json.loads(run.chart_specs)
            except Exception:
                chart_specs = []

        response = AnalyzeResponse(
            run_id=run.id,
            status=run.status,
            question=run.question,
            sql_query=run.sql_query,
            insight_json=insight_json,
            insight_text=run.output_text,
            output_text=run.output_text,
            chart_specs=chart_specs,
            error=run.error_message,
        )

    return ok(response.model_dump())
