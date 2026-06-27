import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, DatasetRow, QuestionRow
from domain.ask import AskRequest, AskResponse
from domain.dataset import ColumnInfo, DatasetResponse


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_dataset_row_round_trips(session):
    schema = {
        "row_count": 12000,
        "columns": [
            {"name": "region", "type": "text", "distinct": 5, "nulls": 0},
            {"name": "revenue", "type": "number", "min": 0, "max": 98000, "nulls": 3},
        ],
    }
    ds = DatasetRow(
        name="sales.csv",
        source_type="csv",
        row_count=12000,
        schema_summary=json.dumps(schema),
    )
    session.add(ds)
    session.commit()

    fetched = session.query(DatasetRow).one()
    assert fetched.id  # uuid default populated
    assert fetched.name == "sales.csv"
    assert fetched.source_type == "csv"
    assert fetched.row_count == 12000
    assert json.loads(fetched.schema_summary) == schema
    assert fetched.created_at is not None


def test_dataset_source_type_defaults_to_csv(session):
    ds = DatasetRow(name="x.csv", row_count=1, schema_summary="{}")
    session.add(ds)
    session.commit()
    assert session.query(DatasetRow).one().source_type == "csv"


def test_question_row_round_trips(session):
    ds = DatasetRow(name="sales.csv", row_count=3, schema_summary="{}")
    session.add(ds)
    session.commit()

    chart = {
        "type": "bar",
        "x": "region",
        "series": [{"region": "West", "revenue": 410000}],
    }
    q = QuestionRow(
        dataset_id=ds.id,
        question="total revenue by region",
        answer_text="The West region had the highest revenue.",
        chart_spec=json.dumps(chart),
        status="completed",
    )
    session.add(q)
    session.commit()

    fetched = session.query(QuestionRow).one()
    assert fetched.id
    assert fetched.dataset_id == ds.id
    assert fetched.question == "total revenue by region"
    assert fetched.answer_text == "The West region had the highest revenue."
    assert json.loads(fetched.chart_spec) == chart
    assert fetched.status == "completed"
    assert fetched.error_message is None
    assert fetched.created_at is not None


def test_question_status_defaults_and_nullables(session):
    ds = DatasetRow(name="x.csv", row_count=1, schema_summary="{}")
    session.add(ds)
    session.commit()

    q = QuestionRow(dataset_id=ds.id, question="hi?")
    session.add(q)
    session.commit()

    fetched = session.query(QuestionRow).one()
    assert fetched.status == "pending"
    assert fetched.answer_text is None
    assert fetched.chart_spec is None
    assert fetched.error_message is None


def test_dataset_response_matches_api_contract():
    # Mirrors spec/api.md POST /datasets response `data` shape exactly.
    payload = {
        "dataset_id": "uuid",
        "name": "sales.csv",
        "row_count": 12000,
        "columns": [
            {"name": "region", "type": "text"},
            {"name": "revenue", "type": "number"},
        ],
    }
    resp = DatasetResponse.model_validate(payload)
    assert resp.model_dump() == payload
    assert resp.columns == [
        ColumnInfo(name="region", type="text"),
        ColumnInfo(name="revenue", type="number"),
    ]


def test_ask_request_matches_api_contract():
    # Mirrors spec/api.md POST /ask request shape exactly.
    payload = {"dataset_id": "uuid", "question": "total revenue by region"}
    req = AskRequest.model_validate(payload)
    assert req.model_dump() == payload


def test_ask_response_matches_api_contract():
    # Mirrors spec/api.md POST /ask response `data` shape exactly.
    payload = {
        "question_id": "uuid",
        "answer_text": "The West region had the highest revenue at $410k...",
        "chart_spec": {
            "type": "bar",
            "x": "region",
            "series": [{"region": "West", "revenue": 410000}],
        },
        "status": "completed",
    }
    resp = AskResponse.model_validate(payload)
    assert resp.model_dump() == payload


def test_ask_response_allows_null_answer_and_chart():
    resp = AskResponse.model_validate({"question_id": "u", "status": "pending"})
    assert resp.answer_text is None
    assert resp.chart_spec is None
    assert resp.status == "pending"
