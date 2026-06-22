from datetime import datetime, timezone

from data_analyst.domain import AuditLogEntry, Dataset, Message, Session


def _now():
    return datetime.now(timezone.utc)


def test_dataset_roundtrip():
    d = Dataset(
        id=1,
        session_id=1,
        name="invoices",
        source_filename="invoices.csv",
        file_format="csv",
        duckdb_table="s1_invoices",
        row_count=10,
        schema_json=[{"name": "amount", "type": "DECIMAL"}],
        sample_rows_json=[{"amount": 1}],
        created_at=_now(),
    )
    assert d.schema_json[0].name == "amount"


def test_message_optional_fields_default_none():
    m = Message(id=1, session_id=1, role="user", content="hi", created_at=_now())
    assert m.generated_sql is None
    assert m.result_table_json is None


def test_audit_entry_status_enum():
    a = AuditLogEntry(
        id=1, session_id=1, duration_ms=12, status="success", created_at=_now()
    )
    assert a.status == "success"


def test_session_from_attributes():
    class Row:
        id = 1
        name = "Q2 review"
        created_at = _now()
        updated_at = _now()

    s = Session.model_validate(Row())
    assert s.name == "Q2 review"
