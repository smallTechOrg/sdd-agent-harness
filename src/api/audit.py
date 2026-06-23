"""Audit-log listing and export endpoints (spec/api.md)."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from api._common import ok
from db.session import get_session

router = APIRouter()

_FIELDS = [
    "id",
    "dataset_id",
    "nl_question",
    "generated_sql",
    "row_count",
    "duration_ms",
    "status",
    "error_message",
    "created_at",
]


def _entry(row) -> dict:
    created = getattr(row, "created_at", None)
    return {
        "id": row.id,
        "dataset_id": getattr(row, "dataset_id", None),
        "nl_question": getattr(row, "nl_question", None),
        "generated_sql": getattr(row, "generated_sql", None),
        "row_count": getattr(row, "row_count", None),
        "duration_ms": getattr(row, "duration_ms", None),
        "status": getattr(row, "status", None),
        "error_message": getattr(row, "error_message", None),
        "created_at": created.isoformat() if created is not None else None,
    }


def _resolve_session_id(db, session_id: str | None) -> str | None:
    if session_id:
        return session_id
    from services import ingest as ingest_svc

    get_default = getattr(ingest_svc, "get_or_create_default_session", None)
    if callable(get_default):
        sess = get_default(db)
        return getattr(sess, "id", None) or (
            sess.get("id") if isinstance(sess, dict) else None
        )
    return None


def _query_entries(db, session_id: str | None, limit: int | None) -> list[dict]:
    from db.models import AuditLogRow

    resolved = _resolve_session_id(db, session_id)
    q = db.query(AuditLogRow)
    if resolved:
        q = q.filter(AuditLogRow.session_id == resolved)
    q = q.order_by(AuditLogRow.created_at.desc())
    if limit:
        q = q.limit(limit)
    return [_entry(r) for r in q.all()]


@router.get("/audit")
def list_audit(
    session_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_session),
) -> dict:
    return ok(_query_entries(db, session_id, limit))


@router.get("/audit/export")
def export_audit(
    session_id: str | None = None,
    format: str = "csv",
    db: Session = Depends(get_session),
):
    entries = _query_entries(db, session_id, None)
    fmt = (format or "csv").lower()

    if fmt == "json":
        body = json.dumps(entries, indent=2)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="audit.json"'},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_FIELDS)
    writer.writeheader()
    for e in entries:
        writer.writerow({k: ("" if e.get(k) is None else e.get(k)) for k in _FIELDS})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )
