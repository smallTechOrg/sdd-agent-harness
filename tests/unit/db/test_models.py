from data_analyst.db.models import (
    AuditLogEntryRow,
    DatasetRow,
    MessageRow,
    SessionRow,
)


def test_create_and_read_session(db_session):
    row = SessionRow(name="Q2 billing review")
    db_session.add(row)
    db_session.commit()

    fetched = db_session.get(SessionRow, row.id)
    assert fetched is not None
    assert fetched.name == "Q2 billing review"
    assert fetched.created_at is not None


def test_dataset_belongs_to_session(db_session):
    s = SessionRow(name="s")
    db_session.add(s)
    db_session.flush()

    d = DatasetRow(
        session_id=s.id,
        name="invoices",
        source_filename="invoices.csv",
        file_format="csv",
        duckdb_table=f"s{s.id}_invoices",
        row_count=42,
        schema_json=[{"name": "amount", "type": "DECIMAL"}],
        sample_rows_json=[{"amount": 1}],
    )
    db_session.add(d)
    db_session.commit()

    assert db_session.get(SessionRow, s.id).datasets[0].name == "invoices"
    assert d.schema_json[0]["name"] == "amount"


def test_message_and_audit_append(db_session):
    s = SessionRow(name="s")
    db_session.add(s)
    db_session.flush()

    db_session.add(
        MessageRow(session_id=s.id, role="user", content="total invoices?")
    )
    db_session.add(
        AuditLogEntryRow(
            session_id=s.id,
            nl_prompt="total invoices?",
            generated_sql="SELECT count(*) FROM s1_invoices",
            row_count=1,
            duration_ms=8,
            status="success",
        )
    )
    db_session.commit()

    sess = db_session.get(SessionRow, s.id)
    assert len(sess.messages) == 1
    assert len(sess.audit_entries) == 1
    assert sess.audit_entries[0].status == "success"


def test_audit_error_entry(db_session):
    s = SessionRow(name="s")
    db_session.add(s)
    db_session.flush()
    db_session.add(
        AuditLogEntryRow(
            session_id=s.id,
            nl_prompt="bad query",
            duration_ms=3,
            status="error",
            error_message="syntax error",
        )
    )
    db_session.commit()
    assert db_session.get(SessionRow, s.id).audit_entries[0].error_message == "syntax error"
