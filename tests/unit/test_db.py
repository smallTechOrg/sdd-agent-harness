"""DB layer tests for the DataChat schema — no LLM key required.

Exercises the ``datasets`` and ``messages`` models against an isolated SQLite
DB (the production driver here): mapping, insert/read round-trip, the
dataset → messages FK relationship, default values, and JSON-column round-trip.
"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from db.models import DatasetRow, MessageRow
from domain import Dataset, Message


def _make_dataset(**overrides) -> DatasetRow:
    data = dict(
        name="sales.csv",
        original_filename="sales.csv",
        file_path="data/uploads/abc.csv",
        profile_json=json.dumps({"row_count": 3, "columns": []}),
    )
    data.update(overrides)
    return DatasetRow(**data)


def test_dataset_roundtrip_and_defaults(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, ds_id)
        assert fetched is not None
        assert fetched.name == "sales.csv"
        assert fetched.original_filename == "sales.csv"
        assert fetched.file_path == "data/uploads/abc.csv"
        # source_kind defaults to 'csv'
        assert fetched.source_kind == "csv"
        # timestamps populated by defaults
        assert fetched.created_at is not None
        assert fetched.updated_at is not None
        # uuid primary key
        assert isinstance(fetched.id, str) and len(fetched.id) >= 32


def test_dataset_profile_json_roundtrips(_isolated_db):
    profile = {
        "row_count": 50000,
        "columns": [
            {"name": "amount", "dtype": "float64", "missing": 2, "min": 0.0, "max": 99.9},
            {"name": "region", "dtype": "object", "missing": 0},
        ],
        "sample_rows": [{"amount": 12.5, "region": "north"}],
    }
    with Session(_isolated_db) as s:
        ds = _make_dataset(profile_json=json.dumps(profile))
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, ds_id)
        loaded = json.loads(fetched.profile_json)
        assert loaded == profile
        assert loaded["row_count"] == 50000
        assert loaded["columns"][0]["name"] == "amount"


def test_message_defaults(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        msg = MessageRow(dataset_id=ds.id, question="What is the average amount?")
        s.add(msg)
        s.commit()
        msg_id = msg.id

    with Session(_isolated_db) as s:
        fetched = s.get(MessageRow, msg_id)
        assert fetched is not None
        assert fetched.question == "What is the average amount?"
        # defaults
        assert fetched.status == "running"
        assert fetched.prompt_tokens == 0
        assert fetched.completion_tokens == 0
        assert fetched.cost_usd == 0.0
        # nullable fields default to None
        assert fetched.plan is None
        assert fetched.generated_code is None
        assert fetched.answer is None
        assert fetched.key_numbers_json is None
        assert fetched.result_table_json is None
        assert fetched.error is None
        assert fetched.completed_at is None
        assert fetched.created_at is not None


def test_message_json_columns_roundtrip(_isolated_db):
    key_numbers = {"average_amount": 42.7, "row_count": 50000}
    result_table = {
        "columns": ["region", "avg_amount"],
        "rows": [["north", 41.2], ["south", 44.1]],
    }
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        msg = MessageRow(
            dataset_id=ds.id,
            question="avg by region?",
            key_numbers_json=json.dumps(key_numbers),
            result_table_json=json.dumps(result_table),
        )
        s.add(msg)
        s.commit()
        msg_id = msg.id

    with Session(_isolated_db) as s:
        fetched = s.get(MessageRow, msg_id)
        assert json.loads(fetched.key_numbers_json) == key_numbers
        assert json.loads(fetched.result_table_json) == result_table


def test_message_lifecycle_running_to_completed(_isolated_db):
    """A message is written 'running' and updated exactly once to terminal."""
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        msg = MessageRow(dataset_id=ds.id, question="q")
        s.add(msg)
        s.commit()
        msg_id = msg.id

    with Session(_isolated_db) as s:
        msg = s.get(MessageRow, msg_id)
        assert msg.status == "running"
        msg.status = "completed"
        msg.answer = "The average is 42.7."
        msg.plan = "1. group by region\n2. mean of amount"
        msg.generated_code = "result = df.groupby('region')['amount'].mean()"
        msg.prompt_tokens = 120
        msg.completion_tokens = 80
        msg.cost_usd = 0.0004
        msg.completed_at = datetime.now(timezone.utc)
        s.commit()

    with Session(_isolated_db) as s:
        msg = s.get(MessageRow, msg_id)
        assert msg.status == "completed"
        assert msg.answer == "The average is 42.7."
        assert msg.prompt_tokens == 120
        assert msg.completion_tokens == 80
        assert msg.cost_usd == 0.0004
        assert msg.completed_at is not None


def test_message_failed_status_captures_error(_isolated_db):
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        msg = MessageRow(
            dataset_id=ds.id,
            question="q",
            status="failed",
            error="Traceback: KeyError 'nonexistent_column'",
            generated_code="result = df['nonexistent_column'].mean()",
        )
        s.add(msg)
        s.commit()
        msg_id = msg.id

    with Session(_isolated_db) as s:
        msg = s.get(MessageRow, msg_id)
        assert msg.status == "failed"
        assert "KeyError" in msg.error
        assert msg.generated_code is not None


def test_dataset_messages_relationship(_isolated_db):
    """A dataset has many messages, ordered by created_at, linked by dataset_id."""
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        ds_id = ds.id
        for i in range(3):
            s.add(MessageRow(dataset_id=ds_id, question=f"question {i}"))
        s.commit()

    with Session(_isolated_db) as s:
        ds = s.get(DatasetRow, ds_id)
        assert len(ds.messages) == 3
        # all messages point back at this dataset
        assert all(m.dataset_id == ds_id for m in ds.messages)
        # back_populates wires the reverse relationship
        assert all(m.dataset.id == ds_id for m in ds.messages)
        questions = {m.question for m in ds.messages}
        assert questions == {"question 0", "question 1", "question 2"}


def test_messages_scoped_per_dataset(_isolated_db):
    """Two datasets keep independent threads — no cross-talk."""
    with Session(_isolated_db) as s:
        ds_a = _make_dataset(name="a.csv")
        ds_b = _make_dataset(name="b.csv")
        s.add_all([ds_a, ds_b])
        s.commit()
        a_id, b_id = ds_a.id, ds_b.id
        s.add(MessageRow(dataset_id=a_id, question="only A"))
        s.add(MessageRow(dataset_id=b_id, question="B one"))
        s.add(MessageRow(dataset_id=b_id, question="B two"))
        s.commit()

    with Session(_isolated_db) as s:
        a = s.get(DatasetRow, a_id)
        b = s.get(DatasetRow, b_id)
        assert len(a.messages) == 1
        assert len(b.messages) == 2
        assert a.messages[0].question == "only A"


def test_unique_ids_across_rows(_isolated_db):
    with Session(_isolated_db) as s:
        datasets = [_make_dataset(name=f"d{i}.csv") for i in range(3)]
        s.add_all(datasets)
        s.commit()
        ids = [d.id for d in datasets]
    assert len(set(ids)) == 3


def test_dataset_pydantic_view_from_row(_isolated_db):
    """The Dataset Pydantic model mirrors a DatasetRow for API serialization."""
    with Session(_isolated_db) as s:
        ds = _make_dataset()
        s.add(ds)
        s.commit()
        view = Dataset(
            id=ds.id,
            name=ds.name,
            original_filename=ds.original_filename,
            file_path=ds.file_path,
            profile=json.loads(ds.profile_json),
            source_kind=ds.source_kind,
            created_at=ds.created_at,
            updated_at=ds.updated_at,
        )
    assert view.id == ds.id
    assert view.source_kind == "csv"
    assert view.profile["row_count"] == 3
    # JSON-serializable for the API envelope
    dumped = view.model_dump(mode="json")
    assert dumped["name"] == "sales.csv"
    assert dumped["profile"]["row_count"] == 3


def test_message_pydantic_view_defaults():
    """The Message Pydantic model exposes the run fields with sane defaults."""
    m = Message(
        id="m1",
        dataset_id="d1",
        question="avg?",
        created_at=datetime.now(timezone.utc),
    )
    assert m.status == "running"
    assert m.prompt_tokens == 0
    assert m.completion_tokens == 0
    assert m.cost_usd == 0.0
    assert m.key_numbers == {}
    assert m.result_table is None
    assert m.completed_at is None
    dumped = m.model_dump(mode="json")
    assert dumped["question"] == "avg?"
    assert dumped["status"] == "running"
