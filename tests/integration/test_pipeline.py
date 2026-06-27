"""Integration test — the real DataChat pipeline end-to-end via run_agent.

Requires a real LLM key (Gemini). Loads the sales fixture into the local DuckDB
store, registers the DatasetRow, then runs the agent graph for real and asserts
the persisted QuestionRow is completed with a real answer + chart spec.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from db.models import DatasetRow, QuestionRow

FIXTURE = Path(__file__).resolve().parent.parent / "phase1" / "fixtures" / "sales.csv"


@pytest.fixture(autouse=True)
def _isolated_duckdb(tmp_path, monkeypatch):
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", str(tmp_path / "working.duckdb"))
    import tools.duckdb_store as ds
    ds._conn = None
    ds._conn_path = None
    yield
    ds._conn = None
    ds._conn_path = None


def _seed_dataset(engine, dataset_id: str) -> None:
    from tools.duckdb_store import load_csv
    from tools.profile import build_schema_summary

    row_count = load_csv(str(FIXTURE), dataset_id)
    summary = build_schema_summary(dataset_id)
    with Session(engine) as s:
        s.add(
            DatasetRow(
                id=dataset_id,
                name="sales.csv",
                source_type="csv",
                row_count=row_count,
                schema_summary=json.dumps(summary),
            )
        )
        s.commit()


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_runs_end_to_end(_isolated_db):
    from graph.runner import run_agent

    dataset_id = "ds-integration-1"
    _seed_dataset(_isolated_db, dataset_id)

    question_id = run_agent(dataset_id, "total revenue by region")
    assert question_id

    with Session(_isolated_db) as s:
        q = s.get(QuestionRow, question_id)

    assert q is not None
    assert q.status == "completed", f"failed: {q.error_message}"
    assert q.answer_text and len(q.answer_text) > 5
    assert q.chart_spec
    chart = json.loads(q.chart_spec)
    assert isinstance(chart, dict) and chart.get("type")
    assert q.error_message is None


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_persists_question_text(_isolated_db):
    from graph.runner import run_agent

    dataset_id = "ds-integration-2"
    _seed_dataset(_isolated_db, dataset_id)

    question = "total revenue by region"
    question_id = run_agent(dataset_id, question)

    with Session(_isolated_db) as s:
        q = s.get(QuestionRow, question_id)
    assert q.question == question
    assert q.dataset_id == dataset_id
