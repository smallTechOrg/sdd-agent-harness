"""DB layer tests — no LLM key required."""
import json

from sqlalchemy.orm import Session

from db.models import RunRow, DatasetRow
import db.session as session_module


def test_run_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        run = RunRow(dataset_id="ds-1", question="What is the total?")
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        fetched = s.get(RunRow, run_id)
        assert fetched is not None
        assert fetched.dataset_id == "ds-1"
        assert fetched.question == "What is the total?"
        assert fetched.status == "pending"
        assert fetched.chart_type is None


def test_run_row_analysis_columns(_isolated_db):
    """RunRow can store and retrieve chart data columns."""
    with Session(_isolated_db) as s:
        run = RunRow(
            dataset_id="ds-2",
            question="Revenue by month?",
            status="completed",
            chart_type="bar",
            labels_json=json.dumps(["Jan", "Feb", "Mar"]),
            values_json=json.dumps([1000.0, 2000.0, 3000.0]),
            summary="Revenue grew over three months.",
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(RunRow, run_id)
        assert run.status == "completed"
        assert run.chart_type == "bar"
        assert json.loads(run.labels_json) == ["Jan", "Feb", "Mar"]
        assert json.loads(run.values_json) == [1000.0, 2000.0, 3000.0]
        assert run.summary == "Revenue grew over three months."


def test_dataset_row_roundtrip(_isolated_db):
    """DatasetRow stores and retrieves schema and sample data."""
    columns = [{"name": "month", "dtype": "object"}, {"name": "revenue", "dtype": "int64"}]
    sample = [{"month": "January", "revenue": 12000}]

    with Session(_isolated_db) as s:
        ds = DatasetRow(
            filename="sales.csv",
            file_path="/tmp/sales.csv",
            columns_json=json.dumps(columns),
            sample_rows_json=json.dumps(sample),
            row_count=25,
        )
        s.add(ds)
        s.commit()
        ds_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, ds_id)
        assert fetched is not None
        assert fetched.filename == "sales.csv"
        assert fetched.row_count == 25
        loaded_columns = json.loads(fetched.columns_json)
        assert loaded_columns[0]["name"] == "month"


def test_multiple_datasets_independent(_isolated_db):
    ids = []
    with Session(_isolated_db) as s:
        for i in range(3):
            ds = DatasetRow(
                filename=f"file_{i}.csv",
                file_path=f"/tmp/file_{i}.csv",
                columns_json=json.dumps([{"name": "x", "dtype": "int64"}]),
                sample_rows_json=json.dumps([]),
                row_count=i,
            )
            s.add(ds)
        s.commit()
        datasets = s.query(DatasetRow).all()
        ids = [d.id for d in datasets]

    assert len(ids) == 3
    assert len(set(ids)) == 3  # all unique
