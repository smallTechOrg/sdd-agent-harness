"""DB layer tests — no LLM key required."""
import json

from sqlalchemy.orm import Session
from db.models import RunRow, DatasetRow


def test_run_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        run = RunRow(question="hello world", input_text="hello world")
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        fetched = s.get(RunRow, run_id)
        assert fetched is not None
        assert fetched.question == "hello world"
        assert fetched.status == "pending"
        assert fetched.output_text is None
        assert fetched.sql is None
        assert fetched.result_json is None
        assert fetched.tokens_json is None


def test_run_row_analysis_fields(_isolated_db):
    with Session(_isolated_db) as s:
        run = RunRow(
            dataset_id="ds-1",
            question="What is the total?",
            sql="SELECT sum(x) FROM data;",
            result_json=json.dumps([{"total": 42}]),
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(RunRow, run_id)
        run.status = "completed"
        run.output_text = "The total is 42."
        s.commit()

    with Session(_isolated_db) as s:
        run = s.get(RunRow, run_id)
        assert run.status == "completed"
        assert run.dataset_id == "ds-1"
        assert json.loads(run.result_json) == [{"total": 42}]


def test_dataset_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        ds = DatasetRow(
            name="sales.csv",
            duckdb_path="/data/duckdb/abc.duckdb",
            table_name="data",
            schema_json=json.dumps([{"name": "revenue", "type": "DOUBLE"}]),
            row_count=12,
        )
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        ds = s.get(DatasetRow, ds_id)
        assert ds is not None
        assert ds.name == "sales.csv"
        assert ds.table_name == "data"
        assert ds.row_count == 12
        assert ds.profile_json is None
        assert json.loads(ds.schema_json)[0]["name"] == "revenue"


def test_multiple_runs_independent(_isolated_db):
    with Session(_isolated_db) as s:
        for i in range(3):
            s.add(RunRow(question=f"q {i}"))
        s.commit()
        runs = s.query(RunRow).all()
        ids = [r.id for r in runs]

    assert len(ids) == 3
    assert len(set(ids)) == 3
