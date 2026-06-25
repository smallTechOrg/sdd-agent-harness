"""Integration test: stubbed pipeline runs end-to-end with no OpenRouter key."""
import csv

import pytest

import data_analysis_agent.db.session as session_module
from data_analysis_agent.db.database import Database
from data_analysis_agent.db.models import (
    DataSourceRow, SessionDataSourceRow,
    SessionRow, QueryRecordRow, AgentRunRow,
)
from data_analysis_agent.tools.ingester import FileIngester


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("DATAANALYSIS_DATABASE_URL", "sqlite:///stub_test.db")
    monkeypatch.setenv("DATAANALYSIS_OPENROUTER_API_KEY", "")


@pytest.fixture(autouse=True)
def _use_sqlite(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    db._init_schema()

    monkeypatch.setattr(session_module, "_db", db)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    monkeypatch.setenv("DATAANALYSIS_CHECKPOINT_DB", str(tmp_path / "ckpt.db"))

    yield

    db._dispose()
    monkeypatch.setattr(session_module, "_db", None)


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "sample.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["region", "sales", "units"])
        writer.writerow(["North", 10000, 50])
        writer.writerow(["South", 8000, 40])
        writer.writerow(["East", 12000, 60])
    return str(path)


@pytest.fixture
def session_and_query(csv_file, tmp_path):
    result = FileIngester().ingest(csv_file, tmp_path / "parquet", "sample_ds")
    with session_module.create_db_session() as db:
        ds = DataSourceRow(
            name="sample.csv",
            type="csv",
            parquet_path=result.parquet_path,
            row_count=result.row_count,
            schema_json=result.schema_json,
            tool_description="Execute SQL SELECT queries against the dataset.",
            capability_description="Execute a SQL SELECT statement. Table name is 'sample'.",
        )
        ds.column_names = result.column_names
        db.add(ds)
        db.flush()

        sess = SessionRow(name="Test session")
        db.add(sess)
        db.flush()

        db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds.id))
        db.flush()

        qr = QueryRecordRow(session_id=sess.id, question="What is the total sales?")
        db.add(qr)
        db.flush()

        return sess.id, qr.id


def test_pipeline_runs_end_to_end(session_and_query):
    from data_analysis_agent.graph.runner import run_pipeline

    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None

    session_id, query_record_id = session_and_query
    final_state = run_pipeline(
        query_record_id=query_record_id,
        session_id=session_id,
        question="What is the total sales?",
    )

    assert final_state.get("error") is None, f"Pipeline error: {final_state.get('error')}"

    with session_module.create_db_session() as s:
        qr = s.get(QueryRecordRow, query_record_id)
        assert qr is not None
        assert qr.status == "completed"
        assert qr.answer is not None
        assert len(qr.answer) > 0
        assert qr.iteration_count == 1

        runs = s.query(AgentRunRow).filter_by(query_record_id=query_record_id).all()
        assert len(runs) == 1
        assert runs[0].status == "completed"


def _add_query(session_id: str, question: str) -> str:
    with session_module.create_db_session() as db:
        qr = QueryRecordRow(session_id=session_id, question=question)
        db.add(qr)
        db.flush()
        return qr.id


def test_session_memory_accumulates_across_queries(session_and_query):
    """Two queries in one session → the durable `conversation` carries both turns."""
    from data_analysis_agent.graph.runner import run_pipeline

    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None

    session_id, qr1 = session_and_query
    run_pipeline(query_record_id=qr1, session_id=session_id, question="What is the total sales?")

    qr2 = _add_query(session_id, "And the average?")
    final2 = run_pipeline(query_record_id=qr2, session_id=session_id, question="And the average?")

    convo = final2.get("conversation", [])
    assert [t["question"] for t in convo] == ["What is the total sales?", "And the average?"], convo
