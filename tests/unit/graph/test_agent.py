"""Unit tests for the DataChat plan-execute graph — NO network.

Covers:
- the graph compiles (``agentic_ai``)
- the conditional edges route correctly: an injected ``error`` -> handle_error,
  and ``route_after_execute`` for the exec_error / retry / ok cases
- the privacy chokepoint: ``build_llm_context`` output is bounded by the
  sample-row cap regardless of file size, and never contains full-data markers
- node-level behaviour with ``LLMClient`` monkeypatched (no real Gemini call):
  plan -> code -> execute (real local sandbox) -> synthesize, and the
  self-correction loop terminating after one retry into handle_error
"""

from __future__ import annotations

import pandas as pd
import pytest

from graph.agent import agentic_ai
from graph.context import build_llm_context
from graph.edges import route_after_execute
from graph.state import AgentState


# --------------------------------------------------------------------------- #
# graph compiles
# --------------------------------------------------------------------------- #

def test_graph_compiles():
    assert agentic_ai is not None
    # The plan-execute topology is present.
    node_names = set(agentic_ai.get_graph().nodes)
    for expected in {
        "profile_context",
        "plan",
        "generate_code",
        "execute_local",
        "synthesize",
        "finalize",
        "handle_error",
    }:
        assert expected in node_names, f"missing node {expected}"


# --------------------------------------------------------------------------- #
# route_after_execute — the self-correction edge
# --------------------------------------------------------------------------- #

def test_route_after_execute_ok_goes_to_synthesize():
    state: AgentState = {"exec_error": None, "retry_count": 0}
    assert route_after_execute(state) == "synthesize"


def test_route_after_execute_first_failure_retries_generate_code():
    # exec_error present, retries not yet exhausted -> retry generate_code.
    state: AgentState = {"exec_error": "KeyError: 'x'", "retry_count": 0}
    assert route_after_execute(state) == "generate_code"


def test_route_after_execute_exhausted_retries_handle_error():
    # exec_error present, retries exhausted (>= AGENT_MAX_RETRIES=1) -> handle_error.
    state: AgentState = {"exec_error": "KeyError: 'x'", "retry_count": 1}
    assert route_after_execute(state) == "handle_error"


# --------------------------------------------------------------------------- #
# error gate routing (the inline lambdas mirror these)
# --------------------------------------------------------------------------- #

def test_injected_error_routes_to_handle_error_via_graph():
    """A fatal error injected at profile_context flows to a failed terminal.

    We monkeypatch the plan node's LLM to raise so ``error`` is set and the
    plan->handle_error edge fires; finalize is never reached.
    """
    import graph.nodes as nodes

    class _Boom:
        def call_model_with_usage(self, *a, **k):
            raise RuntimeError("simulated provider outage")

    original = nodes.LLMClient
    nodes.LLMClient = lambda: _Boom()  # type: ignore[assignment]
    try:
        final = agentic_ai.invoke(
            {
                "message_id": "m1",
                "dataset_id": "d1",
                "question": "anything",
                "profile": {"row_count": 1, "columns": [], "sample_rows": []},
                "file_path": "/nonexistent.csv",
                "messages": [],
                "retry_count": 0,
            }
        )
    finally:
        nodes.LLMClient = original  # type: ignore[assignment]

    assert final.get("status") == "failed"
    assert "simulated provider outage" in (final.get("error") or "")
    assert final.get("answer") is None


# --------------------------------------------------------------------------- #
# privacy chokepoint — build_llm_context is bounded
# --------------------------------------------------------------------------- #

def _big_profile(n_rows: int, sample_cap: int) -> dict:
    """A profile claiming a huge row_count but carrying only ``sample_cap`` rows
    (exactly as the real profiler produces it — the sample is already bounded)."""
    columns = [
        {"name": "region", "dtype": "object", "missing": 0, "distinct": 5,
         "sample_values": ["North", "South", "East", "West", "Central"]},
        {"name": "revenue", "dtype": "float64", "missing": 0,
         "min": 0.0, "max": 9999.0, "mean": 1000.0},
    ]
    sample_rows = [{"region": "North", "revenue": float(i)} for i in range(sample_cap)]
    return {"row_count": n_rows, "columns": columns, "sample_rows": sample_rows}


def test_context_is_bounded_regardless_of_file_size():
    """A 60k-row file and a tiny file produce comparably-sized contexts, because
    only the capped sample + schema ever enter the prompt."""
    question = "What is the average revenue by region?"
    small = build_llm_context(_big_profile(6, 20), question, [])
    large = build_llm_context(_big_profile(60_000, 20), question, [])

    # The huge file's context is NOT proportionally huge — it differs only by the
    # row_count digits, so it stays within a small constant of the small one.
    assert abs(len(large) - len(small)) < 50
    # And it does not explode in absolute terms for a 60k-row file.
    assert len(large) < 6000


def test_context_never_exceeds_sample_cap_even_if_profile_carries_more():
    """Defensive re-cap: even a profile that (incorrectly) carries MORE than the
    cap rows is trimmed by build_llm_context before it can reach the model."""
    question = "q"
    # 500 rows in the profile, but the configured cap is 20.
    profile = _big_profile(60_000, 500)
    ctx = build_llm_context(profile, question, [])
    # The serialized sample must contain at most the cap (20) row objects.
    assert ctx.count('"region":') <= 20


def test_context_contains_schema_question_and_sample_but_not_full_data():
    profile = _big_profile(60_000, 20)
    ctx = build_llm_context(profile, "Average revenue by region?", [])
    assert "region" in ctx and "revenue" in ctx
    assert "Average revenue by region?" in ctx
    # The full data is never serialized — only a bounded sample is present.
    assert "60000" in ctx  # the row_count is mentioned (metadata, not the rows)
    # 20 sample rows, never 60000.
    assert ctx.count('"region":') <= 20


def test_context_trims_history_to_recent_turns():
    profile = _big_profile(10, 5)
    history = [
        {"role": "user", "content": f"old question {i}"} for i in range(50)
    ]
    ctx = build_llm_context(profile, "new question", history)
    # Only the most-recent turns survive (AGENT_HISTORY_TURNS default 6); the
    # very first ancient turns must be gone.
    assert "old question 0" not in ctx
    assert "old question 49" in ctx


# --------------------------------------------------------------------------- #
# node behaviour with a fake LLM (no network) — full happy path + retry loop
# --------------------------------------------------------------------------- #

@pytest.fixture
def tiny_csv(tmp_path):
    path = tmp_path / "tiny.csv"
    pd.DataFrame(
        {"region": ["N", "S", "N", "S"], "revenue": [10.0, 20.0, 30.0, 40.0]}
    ).to_csv(path, index=False)
    return str(path)


class _FakeUsage:
    def __init__(self, p=5, c=7):
        self.prompt_tokens = p
        self.completion_tokens = c


class _FakeChunk:
    def __init__(self, text, usage=None):
        self.text = text
        self.usage = usage


def _install_fake_llm(monkeypatch, *, code_text, exec_should_fail_first=False):
    """Install a fake LLMClient producing a fixed plan/code and a streamed answer.

    ``code_text`` is the code the generate_code node returns (already fenced or
    not — the node extracts it). When ``exec_should_fail_first`` is True the
    FIRST generate_code call returns broken code and the SECOND returns
    ``code_text`` (to exercise the self-correction loop).
    """
    import graph.nodes as nodes

    calls = {"generate": 0}

    class _Fake:
        def call_model_with_usage(self, prompt, *, system=None):
            # "planning step" appears ONLY in plan.md (generate_code.md mentions
            # the word "plan" too, so key off the unambiguous marker).
            if "planning step" in (system or "").lower():
                return ("1. Group by region\n2. Mean revenue", _FakeUsage())
            # generate_code
            calls["generate"] += 1
            if exec_should_fail_first and calls["generate"] == 1:
                return ("```python\nresult = df['does_not_exist'].mean()\n```", _FakeUsage())
            return (code_text, _FakeUsage())

        def stream_model(self, prompt, *, system=None):
            yield _FakeChunk("The average ")
            yield _FakeChunk("revenue ")
            yield _FakeChunk("is computed.", usage=_FakeUsage(p=3, c=9))

    monkeypatch.setattr(nodes, "LLMClient", lambda: _Fake())
    return calls


def test_happy_path_state_flows_through_to_completed(monkeypatch, tiny_csv):
    """End-to-end through the graph with a fake LLM but the REAL local sandbox:
    plan, code, computed numbers, streamed answer, completed status."""
    _install_fake_llm(
        monkeypatch,
        code_text="```python\nresult = df.groupby('region')['revenue'].mean()\n```",
    )
    emitted: list[tuple[str, dict]] = []

    final = agentic_ai.invoke(
        {
            "message_id": "m1",
            "dataset_id": "d1",
            "question": "Average revenue by region?",
            "profile": {
                "row_count": 4,
                "columns": [
                    {"name": "region", "dtype": "object", "missing": 0,
                     "distinct": 2, "sample_values": ["N", "S"]},
                    {"name": "revenue", "dtype": "float64", "missing": 0,
                     "min": 10.0, "max": 40.0, "mean": 25.0},
                ],
                "sample_rows": [{"region": "N", "revenue": 10.0}],
            },
            "file_path": tiny_csv,
            "messages": [],
            "retry_count": 0,
            "_emit": lambda ev, data: emitted.append((ev, data)),
        }
    )

    assert final["status"] == "completed"
    assert final["plan"].startswith("1.")
    assert "groupby" in final["generated_code"]
    # The REAL sandbox computed the real group means over the tiny file.
    assert final["key_numbers"]["N"] == pytest.approx(20.0)  # (10+30)/2
    assert final["key_numbers"]["S"] == pytest.approx(30.0)  # (20+40)/2
    assert final["answer"] and "average" in final["answer"].lower()
    assert final["prompt_tokens"] > 0
    assert final["completion_tokens"] > 0
    assert final["cost_usd"] >= 0.0

    # The streaming sink saw status/plan/code/token events in order.
    events = [e for e, _ in emitted]
    assert "status" in events and "plan" in events and "code" in events
    assert events.count("token") >= 3  # one per streamed chunk


def test_self_correction_retries_once_then_succeeds(monkeypatch, tiny_csv):
    """First code is broken -> exec_error -> generate_code retry -> good code
    -> completed. The retry happens exactly once."""
    calls = _install_fake_llm(
        monkeypatch,
        code_text="```python\nresult = df.groupby('region')['revenue'].mean()\n```",
        exec_should_fail_first=True,
    )

    final = agentic_ai.invoke(
        {
            "message_id": "m1",
            "dataset_id": "d1",
            "question": "Average revenue by region?",
            "profile": {"row_count": 4, "columns": [], "sample_rows": []},
            "file_path": tiny_csv,
            "messages": [],
            "retry_count": 0,
        }
    )

    assert final["status"] == "completed"
    assert calls["generate"] == 2  # initial + exactly one self-correction
    assert final["retry_count"] == 1
    assert final["key_numbers"]["N"] == pytest.approx(20.0)


def test_self_correction_exhausted_routes_to_failed(monkeypatch, tiny_csv):
    """Code that ALWAYS fails -> one retry -> still fails -> handle_error with the
    real error + offending code persisted in state (transparency)."""
    import graph.nodes as nodes

    class _AlwaysBroken:
        def call_model_with_usage(self, prompt, *, system=None):
            if "planning step" in (system or "").lower():
                return ("1. do it", _FakeUsage())
            return ("```python\nresult = df['missing_col'].sum()\n```", _FakeUsage())

        def stream_model(self, prompt, *, system=None):
            yield _FakeChunk("unused", usage=_FakeUsage())

    monkeypatch.setattr(nodes, "LLMClient", lambda: _AlwaysBroken())

    final = agentic_ai.invoke(
        {
            "message_id": "m1",
            "dataset_id": "d1",
            "question": "q",
            "profile": {"row_count": 4, "columns": [], "sample_rows": []},
            "file_path": tiny_csv,
            "messages": [],
            "retry_count": 0,
        }
    )

    assert final["status"] == "failed"
    # The real error and the offending code are carried for the runner to persist.
    assert "missing_col" in (final.get("error") or "")
    assert "missing_col" in (final.get("generated_code") or "")
    assert final["retry_count"] == 1  # retried exactly once before failing
