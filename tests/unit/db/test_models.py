"""Tests for SQLAlchemy ORM models: table existence and basic row operations."""
from datetime import datetime, timezone

from analyst.db.models import AuditLogRow, Base, SessionRow


NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_metadata_contains_sessions_table():
    assert "sessions" in Base.metadata.tables


def test_metadata_contains_audit_log_table():
    assert "audit_log" in Base.metadata.tables


def test_sessions_table_has_expected_columns():
    table = Base.metadata.tables["sessions"]
    column_names = {c.name for c in table.columns}
    assert column_names == {"session_id", "created_at", "last_active_at", "state_json"}


def test_audit_log_table_has_expected_columns():
    table = Base.metadata.tables["audit_log"]
    column_names = {c.name for c in table.columns}
    assert column_names == {
        "id", "timestamp", "session_id", "source_question",
        "sql", "row_count", "status", "error_message",
    }


def test_session_row_can_be_inserted_and_queried(test_session):
    row = SessionRow(
        session_id="sess-test-001",
        created_at=NOW,
        last_active_at=NOW,
        state_json="{}",
    )
    test_session.add(row)
    test_session.flush()

    result = test_session.get(SessionRow, "sess-test-001")
    assert result is not None
    assert result.session_id == "sess-test-001"
    assert result.state_json == "{}"


def test_session_row_state_json_default(test_session):
    row = SessionRow(
        session_id="sess-test-002",
        created_at=NOW,
        last_active_at=NOW,
    )
    test_session.add(row)
    test_session.flush()

    result = test_session.get(SessionRow, "sess-test-002")
    assert result is not None
    assert result.state_json == "{}"


def test_audit_log_row_can_be_inserted_and_queried(test_session):
    row = AuditLogRow(
        timestamp=NOW,
        session_id="sess-test-001",
        source_question="How many records?",
        sql="SELECT COUNT(*) FROM data",
        row_count=42,
        status="success",
    )
    test_session.add(row)
    test_session.flush()

    from sqlalchemy import select
    result = test_session.execute(select(AuditLogRow)).scalars().first()
    assert result is not None
    assert result.session_id == "sess-test-001"
    assert result.row_count == 42
    assert result.status == "success"
    assert result.error_message is None


def test_audit_log_row_with_error_message(test_session):
    row = AuditLogRow(
        timestamp=NOW,
        session_id="sess-test-003",
        source_question="Delete everything",
        sql="DELETE FROM data",
        row_count=0,
        status="error",
        error_message="DML not permitted",
    )
    test_session.add(row)
    test_session.flush()

    from sqlalchemy import select
    result = (
        test_session.execute(
            select(AuditLogRow).where(AuditLogRow.session_id == "sess-test-003")
        )
        .scalars()
        .first()
    )
    assert result is not None
    assert result.error_message == "DML not permitted"


def test_multiple_audit_rows_for_same_session(test_session):
    session_id = "sess-multi"
    for i in range(3):
        row = AuditLogRow(
            timestamp=NOW,
            session_id=session_id,
            source_question=f"Question {i}",
            sql=f"SELECT {i} FROM t",
            row_count=i,
            status="success",
        )
        test_session.add(row)
    test_session.flush()

    from sqlalchemy import select
    rows = (
        test_session.execute(
            select(AuditLogRow).where(AuditLogRow.session_id == session_id)
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
