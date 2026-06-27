from pathlib import Path

import pandas as pd
import pytest

from datasets.profile import build_profile
from datasets.storage import save_file
from db.models import AnalysisRow, DatasetRow
from db.session import create_db_session
from graph.runner import run_analysis

FIXTURE = Path(__file__).parent / "fixtures" / "employees.csv"


@pytest.fixture(autouse=True)
def _uploads_under_tmp(tmp_path, monkeypatch):
    import datasets.storage as storage_mod

    monkeypatch.setattr(storage_mod, "UPLOAD_DIR", tmp_path / "uploads")


@pytest.fixture
def _require_gemini():
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")


@pytest.fixture
def ingested_dataset_id():
    """Ingest the fixture via Slice A's contract and persist a datasets row."""
    content = FIXTURE.read_bytes()
    with create_db_session() as session:
        ds = DatasetRow(
            filename="employees.csv",
            file_format="csv",
            local_path="",
            status="ready",
        )
        session.add(ds)
        session.flush()
        dataset_id = ds.id

    local_path = save_file(dataset_id, "csv", content)
    profile = build_profile(local_path)

    with create_db_session() as session:
        ds = session.get(DatasetRow, dataset_id)
        ds.local_path = local_path
        ds.row_count = profile.row_count
        ds.column_count = profile.column_count
        ds.schema_summary = profile.schema_summary.model_dump_json()

    return dataset_id


def test_average_salary_is_computed_not_guessed(_require_gemini, ingested_dataset_id):
    run_id = run_analysis(ingested_dataset_id, "What is the average salary?")

    with create_db_session() as session:
        row = session.get(AnalysisRow, run_id)
        status = row.status
        answer = row.answer
        code = row.generated_code
        steps = row.execution_steps
        result = row.execution_result
        attempts = row.attempts

    assert status == "completed", f"expected completed, got {status!r}"
    assert answer and answer.strip(), "answer must be non-empty plain language"
    assert code and code.strip(), "generated_code must be non-empty"
    assert "salary" in code, "code must reference the real 'salary' column"
    assert steps and steps.strip(), "execution_steps (captured stdout) must be non-empty"
    assert attempts >= 1

    # Ground truth: the answer must MATCH the real pandas mean over the fixture.
    truth = float(pd.read_csv(FIXTURE)["salary"].mean())
    rounded = round(truth)
    # The computed value appears in the executed result and/or the steps/answer.
    haystack = f"{result}\n{steps}\n{answer}"
    assert (
        str(rounded) in haystack
        or f"{truth:.2f}" in haystack
        or f"{truth:.1f}" in haystack
        or str(int(truth)) in haystack
    ), f"computed mean {truth} not found in result/steps/answer: {haystack!r}"
