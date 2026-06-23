"""Audit-logging helper.

Every data operation (every ask) is recorded in ``audit_logs``. The audit row's
id equals the run_id so a pending row can be created at the start of an ask and
finalized at the end via an upsert keyed by id. The audit trail is permanent.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import AuditLogRow


def write_audit(
    db_session: Session,
    *,
    run_id: str,
    session_id: str,
    dataset_id: str | None = None,
    nl_question: str,
    generated_sql: str | None = None,
    row_count: int | None = None,
    duration_ms: int | None = None,
    status: str,
    error_message: str | None = None,
) -> AuditLogRow:
    """Insert or update an :class:`AuditLogRow` (id == ``run_id``).

    Upserts by id: call once to create a ``pending``/``failed``/``completed`` row,
    or call again with the same ``run_id`` to finalize it. The row is added and
    flushed; the caller owns the commit. Returns the persisted row.
    """
    row = db_session.get(AuditLogRow, run_id)
    if row is None:
        row = AuditLogRow(id=run_id)
        db_session.add(row)

    row.session_id = session_id
    row.dataset_id = dataset_id
    row.nl_question = nl_question
    row.generated_sql = generated_sql
    row.row_count = row_count
    row.duration_ms = duration_ms
    row.status = status
    row.error_message = error_message

    db_session.flush()
    return row


def create_audit_pending(
    db_session: Session,
    *,
    run_id: str,
    session_id: str,
    dataset_id: str | None,
    nl_question: str,
) -> AuditLogRow:
    """Create a ``pending`` audit row at the start of an ask."""
    return write_audit(
        db_session,
        run_id=run_id,
        session_id=session_id,
        dataset_id=dataset_id,
        nl_question=nl_question,
        status="pending",
    )


def finalize_audit(
    db_session: Session,
    *,
    run_id: str,
    session_id: str,
    nl_question: str,
    dataset_id: str | None = None,
    generated_sql: str | None = None,
    row_count: int | None = None,
    duration_ms: int | None = None,
    status: str,
    error_message: str | None = None,
) -> AuditLogRow:
    """Finalize an audit row to ``completed`` or ``failed`` (upsert by id)."""
    return write_audit(
        db_session,
        run_id=run_id,
        session_id=session_id,
        dataset_id=dataset_id,
        nl_question=nl_question,
        generated_sql=generated_sql,
        row_count=row_count,
        duration_ms=duration_ms,
        status=status,
        error_message=error_message,
    )


def list_audit(
    db_session: Session, session_id: str, limit: int = 100
) -> list[AuditLogRow]:
    """Return audit rows for a session, newest-first, capped at ``limit``."""
    return (
        db_session.query(AuditLogRow)
        .filter(AuditLogRow.session_id == session_id)
        .order_by(AuditLogRow.created_at.desc(), AuditLogRow.id.desc())
        .limit(max(0, int(limit)))
        .all()
    )
