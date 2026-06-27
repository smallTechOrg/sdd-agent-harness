"""Phase 1 agent-graph slice: the DataChat LangGraph pipeline.

Covers:
  1. The graph compiles/imports without env vars and has the 6 nodes.
  2. A REAL end-to-end run against Gemini (AGENT_GEMINI_API_KEY from .env):
     profile -> plan -> execute_local -> phrase -> finalize, persisting a
     completed QuestionRow with answer_text + chart_spec.
  3. A graph-level privacy assertion: no raw cell value (the sentinel) ever
     reaches the LLM, proven by spying on LLMClient.call_model.

SQLite (app store) isolation comes from the autouse ``_isolated_db`` conftest
fixture (tmp sqlite engine wired into db.session). This file adds DuckDB
(working store) isolation so we never touch data/. The ``_require_llm_key``
conftest fixture gates the real-key tests on the key actually loaded from .env
(pydantic env_file, not os.environ).
"""

import json
import os

import pytest

from db.models import DatasetRow

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sales.csv")
SENTINEL = "SENTINEL_UNIQUE_CELL_XYZ123"


@pytest.fixture
def duckdb_store(tmp_path, monkeypatch):
    """Point the DuckDB working store at an isolated temp file per test."""
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", str(tmp_path / "working.duckdb"))
    import tools.duckdb_store as ds
    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None
    yield ds
    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None


def _seed_dataset(ds) -> str:
    """Load the fixture CSV into DuckDB + create a DatasetRow; return dataset_id."""
    from tools.profile import build_schema_summary
    from db.session import create_db_session

    row_count = ds.load_csv(FIXTURE, "sales_e2e")
    summary = build_schema_summary("sales_e2e")

    dataset_id = "sales_e2e"
    with create_db_session() as session:
        session.add(
            DatasetRow(
                id=dataset_id,
                name="sales.csv",
                source_type="csv",
                row_count=row_count,
                schema_summary=json.dumps(summary),
            )
        )
    return dataset_id


# --- 1. graph topology -------------------------------------------------------

def test_graph_compiles_and_has_six_nodes():
    # Imports without any env vars / API keys.
    from graph.agent import agentic_ai

    assert agentic_ai is not None
    nodes = set(agentic_ai.get_graph().nodes)
    for name in (
        "profile_data", "plan_compute", "execute_local",
        "phrase_answer", "finalize", "handle_error",
    ):
        assert name in nodes, f"missing node {name!r} in {nodes}"


# --- 2. real end-to-end run against Gemini -----------------------------------

def test_run_agent_end_to_end_real_gemini(_require_llm_key, duckdb_store):
    from graph.runner import run_agent
    from db.session import create_db_session
    from db.models import QuestionRow

    dataset_id = _seed_dataset(duckdb_store)

    question_id = run_agent(dataset_id, "total revenue by region")

    with create_db_session() as session:
        q = session.get(QuestionRow, question_id)
        assert q is not None
        assert q.status == "completed", f"status={q.status} error={q.error_message}"
        assert q.answer_text and q.answer_text.strip()

        answer_text = q.answer_text
        chart_spec_raw = q.chart_spec
        chart = json.loads(chart_spec_raw)

    assert chart["type"] == "bar"
    assert chart["x"] == "region"
    regions = {r["region"] for r in chart["series"]}
    assert "West" in regions

    # The answer/chart must never carry a raw note cell (sentinel).
    assert SENTINEL not in answer_text
    assert SENTINEL not in chart_spec_raw


# --- 3. graph-level privacy assertion ----------------------------------------

def test_no_raw_cell_value_reaches_the_llm(_require_llm_key, duckdb_store, monkeypatch):
    """Spy on every LLM call; assert no raw cell value (sentinel) is sent."""
    import llm.client as llm_client

    captured: list[dict] = []
    real_call = llm_client.LLMClient.call_model

    def spy(self, prompt, *, system=None):
        captured.append({"prompt": prompt, "system": system})
        return real_call(self, prompt, system=system)

    monkeypatch.setattr(llm_client.LLMClient, "call_model", spy)

    from graph.runner import run_agent
    from db.session import create_db_session
    from db.models import QuestionRow

    dataset_id = _seed_dataset(duckdb_store)
    question_id = run_agent(dataset_id, "total revenue by region")

    # The run reached the LLM (both plan + phrase, frugal: exactly 2 calls).
    assert len(captured) == 2, f"expected 2 LLM calls (plan + phrase), got {len(captured)}"

    # No raw cell value — the sentinel or any raw note cell — crossed to the LLM.
    for call in captured:
        blob = f"{call['system']}\n{call['prompt']}"
        assert SENTINEL not in blob, "sentinel raw cell leaked into an LLM prompt"
        assert "alpha" not in blob, "raw note cell leaked into an LLM prompt"

    # And the run still completed (the boundary did not break the pipeline).
    with create_db_session() as session:
        q = session.get(QuestionRow, question_id)
        assert q.status == "completed", f"status={q.status} error={q.error_message}"
