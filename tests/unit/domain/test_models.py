"""Tests for Pydantic domain models: construction, serialisation, round-trip."""
from datetime import datetime, timezone

import pytest

from analyst.domain.audit import AuditLogEntry
from analyst.domain.session import ColumnDef, ConversationTurn, DatasetMeta, Session


NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_column_def_construction_and_serialisation():
    col = ColumnDef(name="customer_id", type="integer")
    data = col.model_dump()
    assert data["name"] == "customer_id"
    assert data["type"] == "integer"


def test_column_def_round_trip():
    col = ColumnDef(name="revenue", type="float")
    assert ColumnDef.model_validate(col.model_dump()) == col


def test_dataset_meta_construction():
    meta = DatasetMeta(
        dataset_id="ds-001",
        name="sales",
        original_filename="sales.csv",
        format="csv",
        columns=[ColumnDef(name="id", type="integer"), ColumnDef(name="amount", type="float")],
        row_count=1000,
        size_bytes=20480,
        file_path="/data/datasets/sess-1/sales.csv",
        uploaded_at=NOW,
    )
    assert meta.dataset_id == "ds-001"
    assert len(meta.columns) == 2


def test_dataset_meta_serialisation_includes_all_fields():
    meta = DatasetMeta(
        dataset_id="ds-001",
        name="orders",
        original_filename="orders.csv",
        format="csv",
        columns=[ColumnDef(name="order_id", type="integer")],
        row_count=50,
        size_bytes=1024,
        file_path="/data/datasets/sess-1/orders.csv",
        uploaded_at=NOW,
    )
    data = meta.model_dump()
    assert set(data.keys()) == {
        "dataset_id", "name", "original_filename", "format",
        "columns", "row_count", "size_bytes", "file_path", "uploaded_at",
    }


def test_dataset_meta_round_trip():
    meta = DatasetMeta(
        dataset_id="ds-002",
        name="products",
        original_filename="products.json",
        format="json",
        columns=[ColumnDef(name="sku", type="text")],
        row_count=100,
        size_bytes=2048,
        file_path="/data/datasets/sess-2/products.json",
        uploaded_at=NOW,
    )
    assert DatasetMeta.model_validate(meta.model_dump()) == meta


def test_conversation_turn_construction_with_optional_fields_absent():
    turn = ConversationTurn(
        turn_id="turn-1",
        role="user",
        content="How many orders last month?",
        timestamp=NOW,
    )
    assert turn.sql is None
    assert turn.result_summary is None


def test_conversation_turn_construction_with_all_fields():
    turn = ConversationTurn(
        turn_id="turn-2",
        role="assistant",
        content="Returned 42 row(s).",
        sql="SELECT * FROM orders WHERE month = 5",
        result_summary="Returned 42 row(s).",
        timestamp=NOW,
    )
    assert turn.sql is not None
    assert turn.result_summary == "Returned 42 row(s)."


def test_conversation_turn_round_trip():
    turn = ConversationTurn(
        turn_id="turn-3",
        role="user",
        content="Show me top customers",
        timestamp=NOW,
    )
    assert ConversationTurn.model_validate(turn.model_dump()) == turn


def test_session_construction_with_empty_lists():
    session = Session(
        session_id="sess-abc",
        created_at=NOW,
        last_active_at=NOW,
    )
    assert session.datasets == []
    assert session.conversation == []


def test_session_construction_with_datasets_and_turns():
    dataset = DatasetMeta(
        dataset_id="ds-001",
        name="sales",
        original_filename="sales.csv",
        format="csv",
        columns=[ColumnDef(name="id", type="integer")],
        row_count=100,
        size_bytes=4096,
        file_path="/data/datasets/sess-abc/sales.csv",
        uploaded_at=NOW,
    )
    turn = ConversationTurn(
        turn_id="turn-1",
        role="user",
        content="What is the total revenue?",
        timestamp=NOW,
    )
    session = Session(
        session_id="sess-abc",
        created_at=NOW,
        last_active_at=NOW,
        datasets=[dataset],
        conversation=[turn],
    )
    assert len(session.datasets) == 1
    assert len(session.conversation) == 1


def test_session_serialisation_and_round_trip():
    session = Session(
        session_id="sess-xyz",
        created_at=NOW,
        last_active_at=NOW,
    )
    data = session.model_dump()
    assert data["session_id"] == "sess-xyz"
    assert Session.model_validate(data) == session


def test_audit_log_entry_construction():
    entry = AuditLogEntry(
        timestamp=NOW,
        session_id="sess-abc",
        source_question="How many rows?",
        sql="SELECT COUNT(*) FROM data",
        row_count=1,
        status="success",
    )
    assert entry.status == "success"
    assert entry.error_message is None


def test_audit_log_entry_with_error():
    entry = AuditLogEntry(
        timestamp=NOW,
        session_id="sess-abc",
        source_question="Drop table data",
        sql="DROP TABLE data",
        row_count=0,
        status="error",
        error_message="DML/DDL not allowed",
    )
    assert entry.status == "error"
    assert entry.error_message == "DML/DDL not allowed"


def test_audit_log_entry_is_frozen():
    entry = AuditLogEntry(
        timestamp=NOW,
        session_id="sess-abc",
        source_question="count rows",
        sql="SELECT COUNT(*) FROM t",
        row_count=5,
    )
    with pytest.raises(Exception):
        entry.row_count = 10  # type: ignore[misc]


def test_audit_log_entry_round_trip():
    entry = AuditLogEntry(
        timestamp=NOW,
        session_id="sess-abc",
        source_question="top 5 customers",
        sql="SELECT customer_id FROM orders LIMIT 5",
        row_count=5,
    )
    assert AuditLogEntry.model_validate(entry.model_dump()) == entry
