"""DB schema tests for the Phase-1 Pandora persistence layer.

No LLM key required — these assert the models import, the tables expose the
expected columns, and a Dataset + Question round-trips against an in-memory
SQLite engine (the production driver).
"""
import json

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from db.models import Base, Dataset, Question
from domain import ColumnProfile, DatasetProfile


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_models_import():
    assert Dataset.__tablename__ == "datasets"
    assert Question.__tablename__ == "questions"


def test_datasets_columns():
    engine = _fresh_engine()
    cols = {c["name"] for c in inspect(engine).get_columns("datasets")}
    expected = {
        "id",
        "filename",
        "row_count",
        "column_count",
        "profile_json",
        "suggested_questions_json",
        "parquet_path",
        "upload_path",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert cols == expected
    engine.dispose()


def test_questions_columns():
    engine = _fresh_engine()
    cols = {c["name"] for c in inspect(engine).get_columns("questions")}
    expected = {
        "id",
        "dataset_id",
        "question",
        "code",
        "answer_text",
        "chart_spec_json",
        "summary_table_json",
        "prompt_tokens",
        "completion_tokens",
        "cost_usd",
        "model",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert cols == expected
    engine.dispose()


def test_questions_dataset_id_indexed():
    engine = _fresh_engine()
    indexes = inspect(engine).get_indexes("questions")
    indexed_cols = {tuple(ix["column_names"]) for ix in indexes}
    assert ("dataset_id",) in indexed_cols
    engine.dispose()


def test_dataset_defaults_and_uuid():
    engine = _fresh_engine()
    with Session(engine) as s:
        ds = Dataset(filename="sales.csv", row_count=50000, column_count=6)
        s.add(ds)
        s.commit()
        assert ds.id is not None
        assert len(ds.id) == 36  # uuid4 string
        assert ds.status == "ready"
        assert ds.error_message is None
        assert ds.created_at is not None
        assert ds.updated_at is not None
    engine.dispose()


def test_dataset_and_question_roundtrip():
    engine = _fresh_engine()

    profile = DatasetProfile(
        row_count=3,
        column_count=2,
        columns=[
            ColumnProfile(
                name="region",
                dtype="object",
                null_count=0,
                missing_pct=0.0,
                distinct_count=4,
                safe_to_sample_labels=True,
                example_labels=["North", "South", "East", "West"],
            ),
            ColumnProfile(
                name="revenue",
                dtype="float64",
                null_count=1,
                missing_pct=33.3,
                min=10.0,
                max=99.0,
                mean=54.5,
            ),
        ],
        high_missing_columns=["revenue"],
    )

    with Session(engine) as s:
        ds = Dataset(
            filename="sales.csv",
            row_count=3,
            column_count=2,
            profile_json=profile.model_dump_json(),
            suggested_questions_json=json.dumps(
                ["Total revenue by region?", "Average revenue?"]
            ),
            parquet_path="data/datasets/abc.parquet",
            upload_path="data/uploads/abc.csv",
        )
        s.add(ds)
        s.commit()
        dataset_id = ds.id

        q = Question(
            dataset_id=dataset_id,
            question="What is total revenue by region?",
            code="result = df.groupby('region')['revenue'].sum()",
            answer_text="North leads at 99.",
            chart_spec_json=json.dumps({"type": "bar", "x": "region", "y": "revenue"}),
            summary_table_json=json.dumps(
                {"columns": ["region", "revenue"], "rows": [["North", 99]]}
            ),
            prompt_tokens=120,
            completion_tokens=80,
            cost_usd=0.00012,
            model="gemini-2.5-flash",
            status="completed",
        )
        s.add(q)
        s.commit()
        question_id = q.id

    with Session(engine) as s:
        ds = s.get(Dataset, dataset_id)
        assert ds is not None
        assert ds.filename == "sales.csv"
        assert ds.parquet_path == "data/datasets/abc.parquet"

        # The persisted profile round-trips back into the typed model.
        loaded = DatasetProfile.model_validate_json(ds.profile_json)
        assert loaded.row_count == 3
        assert loaded.high_missing_columns == ["revenue"]
        region_col = next(c for c in loaded.columns if c.name == "region")
        assert region_col.safe_to_sample_labels is True
        assert region_col.example_labels == ["North", "South", "East", "West"]
        revenue_col = next(c for c in loaded.columns if c.name == "revenue")
        assert revenue_col.safe_to_sample_labels is False
        assert revenue_col.mean == 54.5

        assert json.loads(ds.suggested_questions_json)[0] == "Total revenue by region?"

        q = s.get(Question, question_id)
        assert q is not None
        assert q.dataset_id == dataset_id
        assert q.status == "completed"
        assert q.prompt_tokens == 120
        assert q.completion_tokens == 80
        assert q.cost_usd == 0.00012
        assert q.model == "gemini-2.5-flash"
        assert json.loads(q.chart_spec_json)["type"] == "bar"

    engine.dispose()


def test_question_defaults():
    engine = _fresh_engine()
    with Session(engine) as s:
        ds = Dataset(filename="x.csv", row_count=1, column_count=1)
        s.add(ds)
        s.commit()
        q = Question(dataset_id=ds.id, question="hi")
        s.add(q)
        s.commit()
        assert q.status == "pending"
        assert q.prompt_tokens == 0
        assert q.completion_tokens == 0
        assert q.cost_usd == 0.0
        assert q.code is None
        assert q.model is None
    engine.dispose()
