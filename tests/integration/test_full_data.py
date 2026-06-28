"""Full-dataset correctness gate — REAL Gemini (key from .env; skips if absent).

Phase-1 gate (spec/roadmap.md, harness/patterns/test-driven.md "Full-Data Gates"):
prove the sandbox executes the generated pandas on the **entire** dataset, not a
head/sample the LLM is asked to describe.

The fixture is 50,000 rows. The first ~49,995 rows carry a tiny `amount` (1); a
handful of large outliers (1,000,000) sit DEEP in the data (the last 5 rows). So:

  * full-data ``sum(amount)``  = 49,995 * 1 + 5 * 1,000,000 = 5,049,995
  * full-data ``max(amount)``  = 1,000,000

Any plausible head/sample (e.g. the first 1,000 rows) yields sum ~= 1,000 and
max == 1 — observably different. Asserting the precomputed full-data answer
appears therefore proves the FULL dataset was processed.

A unique SENTINEL also lives in a deep, high-cardinality column the question
never references; it must never reach Gemini (privacy boundary at scale).

Kept under ~30s: the 50k-row pandas op is microseconds; the LLM call is the cost
(one question, max two whole-run attempts to absorb LLM nondeterminism).
"""

import json
import uuid

import numpy as np
import pandas as pd
import pytest

# Fixture parameters (kept here so the expected answer is auditable).
N_ROWS = 50_000
N_OUTLIERS = 5
OUTLIER_VALUE = 1_000_000
BASE_VALUE = 1

# Pre-computed FULL-DATA answers (differ materially from any head/sample).
EXPECTED_SUM = (N_ROWS - N_OUTLIERS) * BASE_VALUE + N_OUTLIERS * OUTLIER_VALUE  # 5,049,995
EXPECTED_MAX = OUTLIER_VALUE  # 1,000,000

# Unique per run — lives only in a deep raw row; must never reach the LLM.
SENTINEL = f"SENTINEL-{uuid.uuid4().hex}"


@pytest.fixture
def _force_gemini():
    from config.settings import get_settings

    s = get_settings()
    if not s.gemini_api_key:
        pytest.skip("No AGENT_GEMINI_API_KEY set in .env — skipping real-Gemini test.")
    s.llm_provider = "gemini"
    if not s.llm_model:
        s.llm_model = "gemini-2.5-flash"
    yield


@pytest.fixture
def _large_dataset(_isolated_db, tmp_path):
    """50,000-row Parquet whose full-data sum/max can ONLY come from full data."""
    amount = np.full(N_ROWS, BASE_VALUE, dtype="int64")
    # Outliers buried at the very end — invisible to any head/sample.
    amount[-N_OUTLIERS:] = OUTLIER_VALUE

    txn_id = np.array([f"t{i}" for i in range(N_ROWS)], dtype=object)
    # Sentinel buried deep in a high-cardinality column the question never uses.
    txn_id[-1] = SENTINEL

    df = pd.DataFrame({"amount": amount, "txn_id": txn_id})

    # Sanity: the precomputed answers really require the full data.
    assert int(df["amount"].sum()) == EXPECTED_SUM
    assert int(df["amount"].max()) == EXPECTED_MAX
    assert int(df.head(1000)["amount"].sum()) != EXPECTED_SUM
    assert int(df.head(1000)["amount"].max()) != EXPECTED_MAX

    parquet_path = tmp_path / "large.parquet"
    df.to_parquet(parquet_path)

    profile = {
        "row_count": N_ROWS,
        "column_count": 2,
        "columns": [
            {
                "name": "amount",
                "dtype": "int64",
                "missing_pct": 0.0,
                "min": int(BASE_VALUE),
                "max": int(OUTLIER_VALUE),
            },
            {
                "name": "txn_id",
                "dtype": "object",
                "missing_pct": 0.0,
                "distinct_count": N_ROWS,
                "safe_to_sample_labels": False,  # high-cardinality — NO example labels
            },
        ],
    }

    from db.session import create_db_session
    from db.models import Dataset

    with create_db_session() as session:
        ds = Dataset(
            filename="large.csv",
            row_count=N_ROWS,
            column_count=2,
            profile_json=json.dumps(profile),
            parquet_path=str(parquet_path),
            status="ready",
        )
        session.add(ds)
        session.flush()
        dataset_id = ds.id
    return dataset_id


def _flatten(final: dict) -> str:
    """All numeric-bearing surfaces of a final answer, as one searchable string."""
    return " ".join(
        [
            json.dumps(final.get("summary_table") or {}),
            final.get("answer_text") or "",
        ]
    )


def test_full_data_sum_requires_entire_dataset(_force_gemini, _large_dataset, monkeypatch):
    """The agent's reported total must equal the FULL-DATA sum (5,049,995)."""
    from graph.runner import run_agent_stream
    from llm.client import LLMClient

    sent_prompts: list[str] = []
    real_call = LLMClient.call_model

    def _capturing_call(self, prompt, *, system=None):
        sent_prompts.append(prompt or "")
        if system:
            sent_prompts.append(system)
        return real_call(self, prompt, system=system)

    monkeypatch.setattr(LLMClient, "call_model", _capturing_call)

    final = None
    for _attempt in range(2):
        sent_prompts.clear()
        events = list(
            run_agent_stream(
                _large_dataset,
                "What is the sum of the amount column across ALL rows in the dataset?",
            )
        )
        final = events[-1]
        # Privacy at scale: the deep sentinel must never reach the LLM.
        assert sent_prompts, "no prompts captured"
        for p in sent_prompts:
            assert SENTINEL not in p, "PRIVACY BREACH: deep raw value reached the LLM"
        if final["type"] == "answer" and final["status"] == "completed":
            break

    assert final["type"] == "answer", f"expected answer, got {final}"
    assert final["status"] == "completed"

    flat = _flatten(final)
    # The full-data total (with thousands separators stripped) must appear; the
    # head/sample total (~1000) would NOT. This is the load-bearing assertion.
    normalised = flat.replace(",", "")
    assert str(EXPECTED_SUM) in normalised, (
        f"expected FULL-DATA sum {EXPECTED_SUM} in answer, got: {flat}"
    )
    # Defensive: the head-sample total must not be what was reported as the answer.
    head_sum = (1000 - 0) * BASE_VALUE
    assert str(head_sum) != normalised.strip(), "answer matches a head-sample, not full data"

    # Sentinel must not echo back in code/answer either.
    assert SENTINEL not in (final.get("code") or "")
    assert SENTINEL not in (final.get("answer_text") or "")
