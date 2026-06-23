"""Audit helper tests — isolated SQLite, no LLM key required."""
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from db.models import AuditLogRow
from services.audit import (
    create_audit_pending,
    finalize_audit,
    list_audit,
    write_audit,
)
from services.ingest import get_or_create_default_session


def _session_id(s: Session) -> str:
    sess = get_or_create_default_session(s)
    s.flush()
    return sess.id


def test_write_audit_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        sid = _session_id(s)
        run_id = str(uuid4())
        write_audit(
            s,
            run_id=run_id,
            session_id=sid,
            dataset_id=None,
            nl_question="What were total sales?",
            generated_sql="SELECT SUM(sales) FROM t",
            row_count=1,
            duration_ms=42,
            status="completed",
            error_message=None,
        )
        s.commit()

    with Session(_isolated_db) as s:
        row = s.get(AuditLogRow, run_id)
        assert row is not None
        assert row.nl_question == "What were total sales?"
        assert row.generated_sql == "SELECT SUM(sales) FROM t"
        assert row.row_count == 1
        assert row.duration_ms == 42
        assert row.status == "completed"
        assert row.created_at is not None


def test_pending_then_finalize_upserts_by_id(_isolated_db):
    with Session(_isolated_db) as s:
        sid = _session_id(s)
        run_id = str(uuid4())
        create_audit_pending(
            s,
            run_id=run_id,
            session_id=sid,
            dataset_id=None,
            nl_question="trend?",
        )
        s.commit()

    with Session(_isolated_db) as s:
        row = s.get(AuditLogRow, run_id)
        assert row.status == "pending"

    with Session(_isolated_db) as s:
        finalize_audit(
            s,
            run_id=run_id,
            session_id=sid,
            nl_question="trend?",
            generated_sql="SELECT 1",
            row_count=0,
            duration_ms=10,
            status="completed",
        )
        s.commit()

    with Session(_isolated_db) as s:
        # Still exactly one row (upsert, not insert).
        rows = s.query(AuditLogRow).filter(AuditLogRow.id == run_id).all()
        assert len(rows) == 1
        assert rows[0].status == "completed"
        assert rows[0].generated_sql == "SELECT 1"


def test_list_audit_newest_first(_isolated_db):
    with Session(_isolated_db) as s:
        sid = _session_id(s)
        questions = ["first", "second", "third"]
        for q in questions:
            write_audit(
                s,
                run_id=str(uuid4()),
                session_id=sid,
                nl_question=q,
                status="completed",
            )
            s.commit()
            time.sleep(0.005)  # ensure distinct created_at ordering

    with Session(_isolated_db) as s:
        listed = list_audit(s, sid, limit=10)
        assert [r.nl_question for r in listed] == ["third", "second", "first"]


def test_list_audit_scoped_by_session(_isolated_db):
    with Session(_isolated_db) as s:
        sid = _session_id(s)
        write_audit(
            s, run_id=str(uuid4()), session_id=sid,
            nl_question="mine", status="completed",
        )
        s.commit()

    with Session(_isolated_db) as s:
        listed = list_audit(s, "no-such-session", limit=10)
        assert listed == []
