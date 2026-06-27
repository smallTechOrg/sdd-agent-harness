"""Integration test for the DataChat agent graph — the privacy gate.

Runs a full chat turn end-to-end against the REAL Gemini API (key from .env),
capturing every prompt + system string sent to the LLM, and asserts the central
design fact of this agent: **no raw data row ever appears in any LLM payload** —
only the schema (column names) and locally-computed aggregate figures do.

Skips (never stubs) if AGENT_GEMINI_API_KEY is genuinely absent — a stubbed LLM
would not exercise the gate.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from db import session as session_module
from db.models import Dataset, Message
from data.schema import infer
from graph.runner import run_chat_turn
from llm.client import LLMClient


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
LARGE_ROWS = 600
LARGE_GROUPS = 15


def _write_large_csv(dir_path: str) -> tuple[str, dict]:
    """A >=500-row, >=15-group CSV.

    Columns:
      * region     — the group key (15 distinct values g0..g14)
      * sales      — a numeric metric; per-group sums are deterministic
      * order_id   — a HIGH-CARDINALITY unique id per row (e.g. ORD-000123).
                     It is never grouped or aggregated, so its values must NEVER
                     appear in any LLM payload — they are pure raw-row markers.

    Construction: row i belongs to group f"g{i % LARGE_GROUPS}" and carries
    sales = (i % LARGE_GROUPS) + 1. Per-group sum therefore = (g+1) * count(g).
    The full file is much larger than the 50-row aggregate cap, and any head(50)
    sample under-counts most groups — so a correct answer proves full-file
    aggregation, not a sample.
    """
    regions = [f"g{i % LARGE_GROUPS}" for i in range(LARGE_ROWS)]
    sales = [(i % LARGE_GROUPS) + 1 for i in range(LARGE_ROWS)]
    order_ids = [f"ORD-{i:06d}" for i in range(LARGE_ROWS)]
    df = pd.DataFrame({"region": regions, "sales": sales, "order_id": order_ids})

    path = os.path.join(dir_path, "large.csv")
    df.to_csv(path, index=False)

    full_sum_by_group = {k: int(v) for k, v in df.groupby("region")["sales"].sum().items()}
    expected = {
        "rows": LARGE_ROWS,
        "groups": LARGE_GROUPS,
        "full_sum_by_group": full_sum_by_group,
        "full_total": int(df["sales"].sum()),
        # Raw cell markers that appear ONLY in non-aggregated rows.
        "raw_order_ids": order_ids,
        "all_region_keys": sorted(set(regions)),
    }
    return path, expected


@pytest.fixture
def large_dataset(tmp_path):
    """Create a large CSV on disk + a Dataset row pointing at it.

    Bypasses the upload storage path (this slice doesn't own it): the file lives
    in tmp_path and the Dataset.stored_path / resolve_path are made consistent by
    monkeypatching the upload dir to tmp_path's resolved location.
    """
    path, expected = _write_large_csv(str(tmp_path))
    schema = infer(path)

    # Place the file where resolve_path(dataset_id, "csv") will find it.
    import data.storage as storage

    upload_dir = str(tmp_path / "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    storage.UPLOAD_DIR = upload_dir  # module-level constant used by resolve_path

    dataset_id = "ds-large-fixture"
    stored_path = os.path.join(upload_dir, f"{dataset_id}.csv")
    pd.read_csv(path).to_csv(stored_path, index=False)

    with Session(session_module._engine) as s:
        s.add(
            Dataset(
                id=dataset_id,
                filename="large.csv",
                stored_path=stored_path,
                file_type="csv",
                schema_json=json.dumps(schema),
                row_count=schema["row_count"],
            )
        )
        s.commit()

    return dataset_id, expected, schema


@pytest.fixture
def capture_llm(monkeypatch):
    """Spy on LLMClient.call_model: capture every (prompt, system) sent to Gemini.

    The real call still runs (real Gemini); we only record the payloads.
    """
    payloads: list[str] = []
    original = LLMClient.call_model

    def spy(self, prompt, *, system=None):  # noqa: ANN001
        payloads.append(prompt or "")
        if system:
            payloads.append(system)
        return original(self, prompt, system=system)

    monkeypatch.setattr(LLMClient, "call_model", spy)
    return payloads


# --------------------------------------------------------------------------- #
# The headline privacy + full-file-aggregation test
# --------------------------------------------------------------------------- #
@pytest.mark.usefixtures("_require_llm_key")
def test_chat_turn_no_raw_rows_in_llm_payloads(large_dataset, capture_llm):
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set — privacy gate needs real Gemini")

    dataset_id, expected, schema = large_dataset

    result = run_chat_turn(
        dataset_id=dataset_id,
        question="What are the total sales by region?",
        conversation_id=None,
    )

    # (a) The turn completed with a non-empty answer.
    assert result["answer"], "expected a non-empty answer from the turn"
    assert result["conversation_id"]

    # The LLM was actually called (plan + compose => >= 2 prompts captured).
    assert capture_llm, "no LLM payloads were captured — the LLM was not called"
    blob = "\n".join(capture_llm)

    # (b) NO raw data row appears in ANY payload. The order_id values are unique
    # per raw row and are never grouped/aggregated, so any appearance would mean
    # a raw row leaked. Check a generous sample of them.
    for order_id in expected["raw_order_ids"][:50]:
        assert order_id not in blob, f"raw row marker {order_id!r} leaked into an LLM payload"
    # Belt-and-braces: the literal column name 'order_id' may be sent (it is a
    # schema column), but no actual ORD- value may. Confirm the prefix only ever
    # appears as the column name context, never a concrete id.
    assert "ORD-" not in blob, "a concrete raw order_id value leaked into an LLM payload"

    # The payloads DO carry schema column names (LLM-safe).
    assert "region" in blob and "sales" in blob, "schema columns should be in the payload"

    # The payloads DO carry aggregate numbers (the compose payload has the table).
    largest_group_sum = max(expected["full_sum_by_group"].values())
    assert str(largest_group_sum) in blob, "aggregate figures should reach the compose LLM"

    # (c) Full-file aggregation, not a sample: the assistant's answer must reflect
    # a known full-file group sum. These per-group sums (e.g. 600 for g14) require
    # aggregating ALL rows for the group; a head(50) sample could not produce them.
    normalized_answer = result["answer"].replace(",", "")
    assert _answer_mentions_total(
        normalized_answer, expected
    ), "answer should reflect a full-file aggregate figure"

    # The aggregate table sent to compose covers all 15 groups (full file), and
    # the local aggregation was capped at <= 50 rows (well above 15 here).
    # Verify via the persisted assistant message + chart.
    with Session(session_module._engine) as s:
        msgs = (
            s.query(Message)
            .filter(Message.conversation_id == result["conversation_id"])
            .order_by(Message.created_at, Message.id)
            .all()
        )
    roles = [m.role for m in msgs]
    assert roles == ["user", "assistant"], f"expected user+assistant messages, got {roles}"
    assert msgs[1].content == result["answer"]

    # A "by region" comparison should produce a bar chart with all 15 groups.
    chart = result["chart"]
    assert chart is not None, "a 'by region' comparison should yield a chart"
    assert chart["type"] == "bar"
    assert len(chart["labels"]) == expected["groups"]
    assert len(chart["series"][0]["values"]) == len(chart["labels"])


def _answer_mentions_total(answer: str, expected: dict) -> bool:
    """Fallback grounding check: the answer cites at least one full-file group sum."""
    sums = set(expected["full_sum_by_group"].values())
    return any(str(v) in answer for v in sums)


# --------------------------------------------------------------------------- #
# Edge case 1 — single-value question returns chart: null
# --------------------------------------------------------------------------- #
@pytest.mark.usefixtures("_require_llm_key")
def test_single_value_question_returns_no_chart(large_dataset):
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set")

    dataset_id, expected, _ = large_dataset

    result = run_chat_turn(
        dataset_id=dataset_id,
        question="What were the total sales across the whole dataset?",
        conversation_id=None,
    )
    assert result["answer"], "expected a non-empty answer"
    # A single scalar answer must not force a chart.
    assert result["chart"] is None, f"single-value answer should have chart=None, got {result['chart']}"
    # Grounded in the full-file total (tolerate currency/comma-grouping formatting,
    # e.g. "$4,800"). The digit string must appear once comma separators are stripped.
    normalized = result["answer"].replace(",", "")
    assert str(expected["full_total"]) in normalized, "answer should cite the full-file total"


# --------------------------------------------------------------------------- #
# Edge case 2 — an aggregation error routes to handle_error gracefully (no crash)
# --------------------------------------------------------------------------- #
@pytest.mark.usefixtures("_require_llm_key")
def test_aggregation_error_routes_to_handle_error(large_dataset, monkeypatch):
    """Force the real aggregation engine to raise (as it would for a plan that
    references a non-existent column); the graph must route to handle_error and
    the runner must return a graceful error answer instead of crashing.

    The plan node still runs the REAL Gemini call (so the plan path is real); we
    only make the local aggregation raise, exercising the error edge faithfully.
    """
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set")

    dataset_id, _, _ = large_dataset

    from graph import nodes as nodes_module

    def boom(file_path, plan):  # noqa: ANN001 — mimic data.aggregation.run_plan signature
        raise ValueError("Plan references column(s) not in dataset: ['does_not_exist']")

    monkeypatch.setattr(nodes_module, "run_plan", boom)

    result = run_chat_turn(
        dataset_id=dataset_id,
        question="break it down by a column that does not exist",
        conversation_id=None,
    )

    # Graceful: a user-facing error answer, no chart, no crash.
    assert result["answer"], "handle_error should still produce a user-facing answer"
    assert result["chart"] is None
    # The failed run + error assistant message were persisted.
    with Session(session_module._engine) as s:
        msgs = (
            s.query(Message)
            .filter(Message.conversation_id == result["conversation_id"])
            .order_by(Message.created_at, Message.id)
            .all()
        )
    assert msgs[-1].role == "assistant"
    assert "couldn't" in msgs[-1].content.lower() or "could not" in msgs[-1].content.lower()
