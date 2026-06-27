"""DB layer tests — no LLM key required.

Exercises the data-analysis tables (datasets, analyses) round-trip and the
foreign-key relationship between them.
"""
from sqlalchemy.orm import Session

from db.models import AnalysisRow, DatasetRow


def test_dataset_row_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        ds = DatasetRow(
            filename="employees.csv",
            file_format="csv",
            local_path="data/uploads/employees.csv",
            row_count=42,
            column_count=4,
            schema_summary="salary: int64\ndepartment: object",
        )
        s.add(ds)
        s.commit()
        dataset_id = ds.id

    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, dataset_id)
        assert fetched is not None
        assert fetched.filename == "employees.csv"
        assert fetched.file_format == "csv"
        assert fetched.row_count == 42
        assert fetched.status == "ready"  # default


def test_analysis_row_roundtrip_and_status_update(_isolated_db):
    with Session(_isolated_db) as s:
        ds = DatasetRow(
            filename="sales.csv",
            file_format="csv",
            local_path="data/uploads/sales.csv",
        )
        s.add(ds)
        s.commit()
        dataset_id = ds.id

        analysis = AnalysisRow(dataset_id=dataset_id, question="What is the average salary?")
        s.add(analysis)
        s.commit()
        analysis_id = analysis.id

    # New analyses start pending with empty result fields.
    with Session(_isolated_db) as s:
        row = s.get(AnalysisRow, analysis_id)
        assert row is not None
        assert row.status == "pending"
        assert row.answer is None
        assert row.generated_code is None
        assert row.attempts == 0

    # The runner writes the computed answer / code / steps back to the row.
    with Session(_isolated_db) as s:
        row = s.get(AnalysisRow, analysis_id)
        row.status = "completed"
        row.answer = "The average salary is 50000."
        row.generated_code = "df['salary'].mean()"
        row.execution_steps = "Loaded df; computed mean of salary column."
        row.execution_result = "50000.0"
        row.attempts = 1
        s.commit()

    with Session(_isolated_db) as s:
        row = s.get(AnalysisRow, analysis_id)
        assert row.status == "completed"
        assert row.generated_code == "df['salary'].mean()"
        assert row.execution_result == "50000.0"
        assert row.dataset_id == dataset_id


def test_multiple_datasets_independent(_isolated_db):
    with Session(_isolated_db) as s:
        for i in range(3):
            s.add(
                DatasetRow(
                    filename=f"file{i}.csv",
                    file_format="csv",
                    local_path=f"data/uploads/file{i}.csv",
                )
            )
        s.commit()
        ids = [d.id for d in s.query(DatasetRow).all()]

    assert len(ids) == 3
    assert len(set(ids)) == 3  # all unique
