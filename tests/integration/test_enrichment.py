"""Integration tests for Phase-2 enrichment — REAL Gemini via .env.

Covers the chart spec, summary table, and follow-up suggestions on top of the
Phase-1 answer, plus the auto-profile on upload. Privacy boundary is re-asserted
for the new followups prompt; failure non-regression confirms enrichment is
never fabricated on a failed run. Skipped only if no LLM key is genuinely set.
"""
import json
import re
from pathlib import Path

import pytest

from analysis.ingest import ingest_csv
from db.models import DatasetRow
import db.session as session_module

_SAMPLE = Path(__file__).resolve().parent.parent.parent / "samples" / "sales.csv"

# Raw-row sentinels that appear ONLY in individual source rows, never in an
# aggregate of a grouped-by-region revenue question.
_RAW_SENTINELS = ["1001", "1007", "Widget", "Gadget", "2024-01-05"]


def _seed_dataset(tmp_path) -> str:
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


# --- Upload profiling (HTTP round-trip, real DuckDB) ------------------------


def test_upload_returns_real_profile(api_client):
    content = _SAMPLE.read_bytes()
    up = api_client.post(
        "/datasets", files={"file": ("sales.csv", content, "text/csv")}
    )
    assert up.status_code == 200, up.text
    profile = up.json()["data"]["profile"]
    assert profile is not None
    assert len(profile) == 7  # one entry per column
    by_col = {p["column"]: p for p in profile}
    rev = by_col["revenue"]
    assert rev["null_count"] == 0
    assert rev["distinct_count"] == 12
    assert float(rev["min"]) == 120.0
    assert float(rev["max"]) == 660.0
    assert by_col["region"]["distinct_count"] == 4
    assert "flags" in rev


# --- Grouped question: chart + summary + followups (real Gemini) ------------


@pytest.mark.usefixtures("_require_llm_key")
def test_grouped_question_enriched(_isolated_db, tmp_path):
    from graph.runner import run_analysis

    dataset_id = _seed_dataset(tmp_path)
    res = run_analysis(dataset_id, "What is total revenue by region?")

    assert res["status"] == "completed", res
    assert res["sql"] and res["result"]

    # Chart: a grouped result -> a non-null bar spec keyed on region + a measure.
    chart = res["chart"]
    assert chart is not None, "expected a chart spec for a grouped result"
    assert chart["type"] in ("bar", "line")
    cols = list(res["result"][0].keys())
    assert chart["x"] in cols and chart["y"] in cols
    # The x axis should be the region-ish label, y a numeric measure.
    assert chart["x"].lower().find("region") >= 0 or chart["x"] in cols

    # Summary table: multiple rows, region column left-aligned text.
    table = res["summary_table"]
    assert table is not None
    assert len(table["rows"]) > 1
    assert {c["align"] for c in table["columns"]} <= {"left", "right"}

    # Follow-ups: a list of 2-3 plausible questions.
    fu = res["followups"]
    assert isinstance(fu, list) and 2 <= len(fu) <= 3, fu
    assert all(isinstance(q, str) and q.strip() for q in fu)


# --- Scalar question: chart null, but answer + summary present --------------


@pytest.mark.usefixtures("_require_llm_key")
def test_scalar_question_no_chart(_isolated_db, tmp_path):
    from graph.runner import run_analysis

    dataset_id = _seed_dataset(tmp_path)
    res = run_analysis(dataset_id, "What is the total revenue?")

    assert res["status"] == "completed", res
    assert res["answer"] and res["sql"]
    # A single-scalar result is not chartable.
    assert res["chart"] is None
    # Summary table still present for the one-row result.
    assert res["summary_table"] is not None


# --- Privacy: followups prompt has schema + aggregate, NO raw rows ----------


@pytest.mark.usefixtures("_require_llm_key")
def test_followups_prompt_has_no_raw_rows(_isolated_db, tmp_path, monkeypatch):
    import graph.nodes as nodes

    captured: list[dict] = []
    real_call = nodes.LLMClient.call_model

    def spy(self, prompt, *, system=None):
        captured.append({"prompt": prompt, "system": system})
        return real_call(self, prompt, system=system)

    monkeypatch.setattr(nodes.LLMClient, "call_model", spy)

    dataset_id = _seed_dataset(tmp_path)
    from graph.runner import run_analysis

    res = run_analysis(dataset_id, "What is total revenue by region?")
    assert res["status"] == "completed", res
    assert captured

    all_prompts = "\n".join(c["prompt"] for c in captured)
    # Schema column name present (the model needs schema context).
    assert "revenue" in all_prompts and "region" in all_prompts

    # NO raw-row sentinel may appear in ANY prompt (incl. the followups node).
    for c in captured:
        blob = (c["prompt"] or "") + "\n" + (c["system"] or "")
        for sentinel in _RAW_SENTINELS:
            assert sentinel not in blob, (
                f"raw-row value {sentinel!r} leaked into an LLM prompt"
            )


# --- Failure non-regression: no fabricated enrichment on a failed run -------


@pytest.mark.usefixtures("_require_llm_key")
def test_failed_run_has_null_enrichment(_isolated_db, tmp_path, monkeypatch):
    """Force SQL generation to keep emitting invalid SQL -> run fails.

    A failed run must return null chart/summary/followups and no number.
    """
    import importlib
    import graph.nodes as nodes

    def always_bad(state):
        return {
            **state,
            "sql": "SELECT no_such_col FROM data;",
            "sql_attempts": state.get("sql_attempts", 0) + 1,
        }

    monkeypatch.setattr(nodes, "generate_sql", always_bad)
    import graph.agent as agent_mod
    importlib.reload(agent_mod)
    monkeypatch.setattr("graph.runner.agentic_ai", agent_mod.agentic_ai)

    dataset_id = _seed_dataset(tmp_path)
    from graph.runner import run_analysis

    res = run_analysis(dataset_id, "What is total revenue by region?")

    assert res["status"] == "failed"
    assert res["answer"] is None
    assert res["chart"] is None
    assert res["summary_table"] is None
    assert res["followups"] is None
    assert res["error"]

    importlib.reload(agent_mod)
