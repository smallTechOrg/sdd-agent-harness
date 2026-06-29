"""Integration tests for the analysis path — REAL Gemini via .env.

These exercise the full graph (generate_sql -> execute_sql -> answer -> finalize)
against the real LLM and a real DuckDB engine. They are skipped only if no LLM
key is genuinely present (the skeleton's `_require_llm_key` fixture).
"""
import json
import re
from pathlib import Path

import duckdb
import pytest

from analysis.ingest import ingest_csv
from db.models import DatasetRow
import db.session as session_module

_SAMPLE = Path(__file__).resolve().parent.parent.parent / "samples" / "sales.csv"

# Raw-row sentinel values that must NEVER appear in an LLM prompt (they only
# exist in individual source rows, never in an aggregate of this question).
_RAW_SENTINELS = ["1001", "1007", "Gizmo", "2024-01-05"]


def _seed_dataset(tmp_path) -> str:
    """Ingest the sample CSV and write a DatasetRow into the isolated DB."""
    content = _SAMPLE.read_bytes()
    ingested = ingest_csv("sales.csv", content, data_dir=tmp_path)
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        ds = DatasetRow(
            name="sales.csv",
            duckdb_path=ingested["duckdb_path"],
            table_name=ingested["table_name"],
            schema_json=json.dumps(ingested["schema"]),
            row_count=ingested["row_count"],
        )
        s.add(ds)
        s.commit()
        return ds.id


def _duckdb_path_for(dataset_id: str) -> str:
    from sqlalchemy.orm import Session

    with Session(session_module._engine) as s:
        return s.get(DatasetRow, dataset_id).duckdb_path


@pytest.mark.usefixtures("_require_llm_key")
def test_golden_path_total_revenue_reproducible(_isolated_db, tmp_path):
    from graph.runner import run_analysis

    dataset_id = _seed_dataset(tmp_path)
    res = run_analysis(dataset_id, "What is the total revenue?")

    assert res["status"] == "completed", res
    assert res["sql"], "expected non-empty SQL"
    assert res["result"], "expected non-empty result"
    assert res["error"] is None

    # Reproducibility: run the returned SQL ourselves; the figure must match.
    path = _duckdb_path_for(dataset_id)
    con = duckdb.connect(path, read_only=True)
    cursor = con.execute(res["sql"])
    rows = cursor.fetchall()
    con.close()
    assert rows, "returned SQL produced no rows"
    produced = rows[0][0]
    # The correct sum of the sample's revenue column.
    assert abs(float(produced) - 3990.0) < 0.01, f"SQL produced {produced}"

    # The answer text must contain the figure the SQL produced (3990 / 3,990).
    answer = res["answer"]
    digits = re.sub(r"[^0-9]", "", answer)
    assert "3990" in digits, f"answer missing the figure: {answer}"


@pytest.mark.usefixtures("_require_llm_key")
def test_privacy_boundary_no_raw_rows_in_prompts(_isolated_db, tmp_path, monkeypatch):
    """Inspect EVERY prompt sent to Gemini: schema yes, raw rows no."""
    import graph.nodes as nodes

    captured: list[dict] = []
    real_call = nodes.LLMClient.call_model

    def spy(self, prompt, *, system=None):
        captured.append({"prompt": prompt, "system": system})
        return real_call(self, prompt, system=system)

    monkeypatch.setattr(nodes.LLMClient, "call_model", spy)

    dataset_id = _seed_dataset(tmp_path)
    from graph.runner import run_analysis

    res = run_analysis(dataset_id, "What is the total revenue?")
    assert res["status"] == "completed", res
    assert captured, "no prompts were captured"

    # A schema column name SHOULD appear (the LLM needs the schema).
    all_prompts = "\n".join(c["prompt"] for c in captured)
    assert "revenue" in all_prompts, "schema column name missing from prompts"

    # NO raw-row sentinel value may appear in ANY prompt (system or user).
    for c in captured:
        blob = (c["prompt"] or "") + "\n" + (c["system"] or "")
        for sentinel in _RAW_SENTINELS:
            assert sentinel not in blob, (
                f"raw-row value {sentinel!r} leaked into an LLM prompt"
            )


@pytest.mark.usefixtures("_require_llm_key")
def test_retry_on_sql_error_recovers_or_fails_cleanly(
    _isolated_db, tmp_path, monkeypatch
):
    """Force the first generate_sql to emit invalid SQL.

    The DuckDB error must be fed back; the model then corrects it and succeeds,
    OR retries exhaust and the run is `failed` with NO fabricated number.
    """
    import graph.nodes as nodes

    real_generate = nodes.generate_sql
    state_box = {"calls": 0}

    def flaky_generate(state):
        state_box["calls"] += 1
        if state_box["calls"] == 1:
            # Reference a column that does not exist -> guaranteed DuckDB error.
            return {**state, "sql": "SELECT sum(no_such_column) FROM data;",
                    "sql_attempts": state.get("sql_attempts", 0) + 1}
        # Subsequent calls: real generation, which now sees the fed-back error.
        return real_generate(state)

    monkeypatch.setattr(nodes, "generate_sql", flaky_generate)
    # Rebuild the graph so it binds the patched node.
    import importlib
    import graph.agent as agent_mod
    importlib.reload(agent_mod)
    monkeypatch.setattr("graph.runner.agentic_ai", agent_mod.agentic_ai)

    dataset_id = _seed_dataset(tmp_path)
    from graph.runner import run_analysis

    res = run_analysis(dataset_id, "What is the total revenue?")

    # The first SQL was invalid; we must have retried at least once.
    assert state_box["calls"] >= 2, "no retry occurred on the SQL error"

    if res["status"] == "completed":
        # Recovered: the corrected SQL must reproduce the real figure.
        path = _duckdb_path_for(dataset_id)
        con = duckdb.connect(path, read_only=True)
        rows = con.execute(res["sql"]).fetchall()
        con.close()
        assert abs(float(rows[0][0]) - 3990.0) < 0.01
    else:
        # Exhausted: failure surfaced, NO fabricated number.
        assert res["status"] == "failed"
        assert res["answer"] is None
        assert res["error"]

    # Restore the original graph for other tests.
    importlib.reload(agent_mod)


@pytest.mark.usefixtures("_require_llm_key")
def test_ask_endpoint_end_to_end(api_client):
    """HTTP round-trip: upload the sample CSV, then ask, against real Gemini."""
    content = _SAMPLE.read_bytes()
    up = api_client.post(
        "/datasets",
        files={"file": ("sales.csv", content, "text/csv")},
    )
    assert up.status_code == 200, up.text
    ds = up.json()["data"]
    assert ds["row_count"] == 12
    assert any(c["name"] == "revenue" for c in ds["schema"])
    dataset_id = ds["id"]

    r = api_client.post(
        f"/datasets/{dataset_id}/ask",
        json={"question": "What is the total revenue?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # Full contract shape.
    for key in (
        "run_id", "dataset_id", "status", "question", "answer", "sql",
        "result", "flagged", "error", "chart", "summary_table",
        "followups", "tokens",
    ):
        assert key in data
    assert data["status"] == "completed"
    assert data["sql"]
    assert data["result"]
    digits = re.sub(r"[^0-9]", "", data["answer"])
    assert "3990" in digits, data["answer"]
    assert data["chart"] is None and data["tokens"] is None
