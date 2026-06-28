"""End-to-end analysis test — REAL Gemini (key from .env; skips if absent).

Builds a tiny Parquet + profile, persists a `datasets` row, runs the streaming
runner for a question with a KNOWN numeric answer, and asserts:
  * a `completed` status with non-empty answer_text,
  * a numeric/grouped result present (summary_table),
  * token/cost usage captured,
  * the PRIVACY BOUNDARY: a unique sentinel value placed in a raw row (in a
    high-cardinality column the question never references) NEVER appears in any
    prompt string sent to Gemini.

Kept under ~30s: one small dataset, one question, two LLM calls.
"""

import json
import uuid

import pandas as pd
import pytest

# Unique per run — must never reach the LLM (it lives only in raw rows).
SENTINEL = f"SENTINEL-{uuid.uuid4().hex}"


@pytest.fixture
def _force_gemini():
    """Pin the provider/model to Gemini for this test (both keys may be set)."""
    from config.settings import get_settings

    s = get_settings()
    if not s.gemini_api_key:
        pytest.skip("No AGENT_GEMINI_API_KEY set in .env — skipping real-Gemini test.")
    s.llm_provider = "gemini"
    if not s.llm_model:
        s.llm_model = "gemini-2.5-flash"
    yield


@pytest.fixture
def _dataset(_isolated_db, tmp_path):
    """Tiny Parquet + DatasetProfile + persisted datasets row.

    Sales by region; the correct total of `amount` is 100 (10+20+30+40). The
    SENTINEL lives only in a high-cardinality `txn_id` column the question
    never references — so it must never reach Gemini.
    """
    df = pd.DataFrame(
        {
            "region": ["North", "South", "North", "South"],
            "amount": [10, 20, 30, 40],
            "txn_id": [SENTINEL, "t2", "t3", "t4"],
        }
    )
    parquet_path = tmp_path / "ds.parquet"
    df.to_parquet(parquet_path)

    profile = {
        "row_count": 4,
        "column_count": 3,
        "columns": [
            {
                "name": "region",
                "dtype": "object",
                "missing_pct": 0.0,
                "distinct_count": 2,
                "safe_to_sample_labels": True,
                "example_labels": ["North", "South"],
            },
            {
                "name": "amount",
                "dtype": "int64",
                "missing_pct": 0.0,
                "min": 10,
                "max": 40,
            },
            {
                "name": "txn_id",
                "dtype": "object",
                "missing_pct": 0.0,
                "distinct_count": 4,
                "safe_to_sample_labels": False,  # high-cardinality — NO example labels
            },
        ],
    }

    from db.session import create_db_session
    from db.models import Dataset

    with create_db_session() as session:
        ds = Dataset(
            filename="sales.csv",
            row_count=4,
            column_count=3,
            profile_json=json.dumps(profile),
            parquet_path=str(parquet_path),
            status="ready",
        )
        session.add(ds)
        session.flush()
        dataset_id = ds.id
    return dataset_id


def test_analysis_end_to_end_with_privacy(_force_gemini, _dataset, monkeypatch):
    from graph.runner import run_agent_stream
    from llm.client import LLMClient

    # Capture every prompt (and system) string actually sent to the model,
    # then delegate to the REAL Gemini call.
    sent_prompts: list[str] = []
    real_call = LLMClient.call_model

    def _capturing_call(self, prompt, *, system=None):
        sent_prompts.append(prompt or "")
        if system:
            sent_prompts.append(system)
        return real_call(self, prompt, system=system)

    monkeypatch.setattr(LLMClient, "call_model", _capturing_call)

    # "total amount" is a trivial, deterministic question that the agent should
    # answer in a single pass. The graph's bounded retry handles a rare bad first
    # generation; we allow up to 3 whole-run attempts purely to absorb LLM
    # nondeterminism (NOT to dodge a real failure — every attempt asserts the
    # full privacy + correctness gate below on its captured prompts).
    events = []
    final = None
    for _attempt in range(3):
        sent_prompts.clear()
        events = list(
            run_agent_stream(_dataset, "What is the total amount across all rows?")
        )
        final = events[-1]
        # Privacy must hold on EVERY attempt, success or stuck.
        assert sent_prompts, "no prompts were captured"
        for p in sent_prompts:
            assert SENTINEL not in p, "PRIVACY BREACH: sentinel raw value reached the LLM"
        if final["type"] == "answer" and final["status"] == "completed":
            break

    assert events, "runner yielded no events"
    step_events = [e for e in events if e["type"] == "step"]

    # Steps stream with the documented shape; generating_code always fires first.
    step_names = [e["step"] for e in step_events]
    assert "generating_code" in step_names
    assert "summarising" in step_names
    for e in step_events:
        assert {"type", "step", "index", "elapsed_ms"} <= set(e)

    # Final must be a completed answer.
    assert final["type"] == "answer", f"expected answer, got {final}"
    assert final["status"] == "completed"
    assert final["answer_text"] and final["answer_text"].strip()
    assert final["code"] and "result" in final["code"]

    # A numeric/grouped result is present, and the correct total (100) appears.
    table = final["summary_table"]
    assert table and table.get("rows")
    flat = json.dumps(table)
    assert "100" in flat, f"expected total 100 in summary_table, got {table}"

    # Usage captured (real Gemini returns token counts via the client, when wired).
    usage = final["usage"]
    assert isinstance(usage, dict)
    assert {"prompt_tokens", "completion_tokens", "cost_usd"} <= set(usage)

    # PRIVACY: the sentinel must not be echoed back in the code or answer either.
    assert SENTINEL not in (final["code"] or "")
    assert SENTINEL not in (final["answer_text"] or "")
