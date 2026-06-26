"""Offline unit tests for slice-3b pre-flight + suggestions + C27 session cache.

Zero env vars, no network, in-memory SQLite (via the autouse `_isolated_db`
fixture in conftest). The stub LLM provider drives every call: it branches only
on the injected node tags (`<node:clarify>` -> "proceed", `<node:select>` ->
first schema id, `<node:suggest>` -> "[]").

These tests verify the stub-mode contract and the deterministic cache behaviour;
the REAL-Gemini behaviour (a genuine clarifying question, a correct selection) is
covered by tests/integration/test_preflight_real.py.
"""
from __future__ import annotations

import pandas as pd
import pytest

from db.models import DatasetRow
from db.session import create_db_session
from graph import nodes as nodes_module
from graph.preflight import check_clarification, select_datasets
from graph.suggestions import generate_suggestions


@pytest.fixture(autouse=True)
def _force_stub_provider(monkeypatch):
    """Make `LLMClient` use the offline stub provider for every test here."""
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "stub")
    monkeypatch.delenv("AGENT_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_OPENROUTER_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _clear_session_cache():
    """C27 cache is module-level — clear it around each test for isolation."""
    nodes_module._session_cache.clear()
    yield
    nodes_module._session_cache.clear()


def _make_dataset(uploads_dir, filename: str = "sales.csv", columns=None) -> str:
    cols = columns or {
        "product": ["a", "b", "c", "d"],
        "price": [10.0, 20.0, 30.0, 40.0],
        "qty": [1, 2, 3, 4],
    }
    df = pd.DataFrame(cols)
    with create_db_session() as session:
        row = DatasetRow(
            filename=filename,
            file_path="",
            row_count=len(df),
            col_count=len(df.columns),
            columns_json=list(df.columns),
            content_hash="hash-" + filename,
            format="csv",
            origin="uploaded",
        )
        session.add(row)
        session.flush()
        dataset_id = row.id
        csv_path = uploads_dir / f"{dataset_id}.csv"
        df.to_csv(csv_path, index=False)
        row.file_path = str(csv_path)
    return dataset_id


@pytest.fixture
def uploads_dir(tmp_path, monkeypatch):
    """Point the nodes' uploads dir at a tmp dir so setup can load real files."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(nodes_module, "_uploads_dir", lambda: d)
    return d


# --------------------------------------------------------------------------- #
# check_clarification (C26) — stub returns "proceed" -> None
# --------------------------------------------------------------------------- #


def test_check_clarification_stub_proceeds():
    """The stub `<node:clarify>` reply is "proceed" -> no clarification (None)."""
    schemas = "- sales.csv (id abc): columns [product, price, qty]"
    result = check_clarification("What is the average price?", schemas)
    assert result is None


def test_check_clarification_fails_open(monkeypatch):
    """An LLM error returns None (fail-open) — never blocks the user."""
    import graph.preflight as preflight_module

    class _Boom:
        def call_model(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(preflight_module, "LLMClient", _Boom)
    assert check_clarification("anything", "schemas") is None


# --------------------------------------------------------------------------- #
# select_datasets (C19) — stub returns the first schema id
# --------------------------------------------------------------------------- #


def test_select_datasets_stub_returns_first_id():
    """Stub `<node:select>` echoes the first `id:` in the schema block."""
    schemas = [
        {"id": "ds-one", "filename": "sales.csv", "columns": ["product", "price"]},
        {"id": "ds-two", "filename": "employees.csv", "columns": ["name", "salary"]},
    ]
    selected, reasoning = select_datasets("revenue?", schemas, ["ds-one", "ds-two"])
    assert selected == ["ds-one"]
    assert isinstance(reasoning, str) and reasoning


def test_select_datasets_falls_back_to_all_on_empty():
    """An empty/unusable selection falls back to ALL candidate ids."""
    # No candidates intersect the (empty schema) selection -> fall back to all.
    schemas: list[dict] = []
    candidates = ["ds-one", "ds-two"]
    selected, reasoning = select_datasets("anything", schemas, candidates)
    assert selected == candidates
    assert "all candidate" in reasoning.lower()


def test_select_datasets_drops_hallucinated_ids(monkeypatch):
    """Ids returned by the model that are not candidates are dropped; if none
    remain, fall back to all."""
    import graph.preflight as preflight_module

    class _Hallucinate:
        def call_model(self, *a, **k):
            return '["not-a-real-id"]'

    monkeypatch.setattr(preflight_module, "LLMClient", _Hallucinate)
    candidates = ["real-1", "real-2"]
    selected, _ = select_datasets("q", [{"id": "real-1"}], candidates)
    assert selected == candidates  # hallucinated id dropped -> fall back to all


def test_select_datasets_fails_open(monkeypatch):
    """An LLM error falls back to ALL candidate ids (fail-open)."""
    import graph.preflight as preflight_module

    class _Boom:
        def call_model(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(preflight_module, "LLMClient", _Boom)
    candidates = ["a", "b"]
    selected, reasoning = select_datasets("q", [{"id": "a"}], candidates)
    assert selected == candidates


# --------------------------------------------------------------------------- #
# generate_suggestions — stub returns [] for <node:suggest>
# --------------------------------------------------------------------------- #


def test_generate_suggestions_stub_returns_empty():
    suggestions, t_in, t_out = generate_suggestions("What is the average?", "The average is 25.")
    assert suggestions == []
    # The call was still made, so token estimates are non-negative ints.
    assert isinstance(t_in, int) and t_in >= 0
    assert isinstance(t_out, int) and t_out >= 0


def test_generate_suggestions_blank_inputs_are_noops():
    assert generate_suggestions("", "answer") == ([], 0, 0)
    assert generate_suggestions("question", "") == ([], 0, 0)


def test_generate_suggestions_never_raises(monkeypatch):
    import graph.suggestions as suggestions_module

    class _Boom:
        def call_model(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(suggestions_module, "LLMClient", _Boom)
    assert generate_suggestions("q", "a") == ([], 0, 0)


# --------------------------------------------------------------------------- #
# C27 session DataFrame cache — reuse on a second setup with the same session_id
# --------------------------------------------------------------------------- #


def test_session_cache_reuses_frame_on_second_setup(uploads_dir):
    """A second `setup` for the same (session_id, dataset_id) returns the SAME
    DataFrame object (cache hit), proving no re-read from disk."""
    dataset_id = _make_dataset(uploads_dir)
    session_id = "session-xyz"

    state1 = {
        "run_id": "run-1",
        "dataset_ids": [dataset_id],
        "session_id": session_id,
    }
    out1 = nodes_module.setup(state1)
    assert out1.get("error") is None
    frame1 = nodes_module._dataframes["run-1"]["frames"][0]

    # The cache now holds the frame for this session.
    assert session_id in nodes_module._session_cache
    cached = nodes_module._session_cache[session_id]["frames"][dataset_id]
    assert cached is frame1

    state2 = {
        "run_id": "run-2",
        "dataset_ids": [dataset_id],
        "session_id": session_id,
    }
    out2 = nodes_module.setup(state2)
    assert out2.get("error") is None
    frame2 = nodes_module._dataframes["run-2"]["frames"][0]

    # Same object reused across runs of the same session (cache hit, no re-read).
    assert frame2 is frame1


def test_session_cache_separate_sessions_do_not_share(uploads_dir):
    """Different session_ids get independent cache entries (different df objects)."""
    dataset_id = _make_dataset(uploads_dir)

    nodes_module.setup({"run_id": "r1", "dataset_ids": [dataset_id], "session_id": "s1"})
    nodes_module.setup({"run_id": "r2", "dataset_ids": [dataset_id], "session_id": "s2"})

    f1 = nodes_module._session_cache["s1"]["frames"][dataset_id]
    f2 = nodes_module._session_cache["s2"]["frames"][dataset_id]
    assert f1 is not f2


def test_single_turn_does_not_populate_session_cache(uploads_dir):
    """No session_id -> the per-run path is used; the session cache stays empty."""
    dataset_id = _make_dataset(uploads_dir)
    nodes_module.setup({"run_id": "r-single", "dataset_ids": [dataset_id], "session_id": None})
    assert nodes_module._session_cache == {}
    assert "r-single" in nodes_module._dataframes


def test_session_cache_lru_evicts_oldest(uploads_dir):
    """The session cache is bounded; overflowing it evicts the oldest session."""
    dataset_id = _make_dataset(uploads_dir)
    cap = nodes_module._SESSION_CACHE_MAX

    for i in range(cap + 2):
        nodes_module.setup(
            {"run_id": f"r{i}", "dataset_ids": [dataset_id], "session_id": f"s{i}"}
        )

    assert len(nodes_module._session_cache) <= cap
    # The two oldest sessions were evicted.
    assert "s0" not in nodes_module._session_cache
    assert "s1" not in nodes_module._session_cache
    # The most-recent session is retained.
    assert f"s{cap + 1}" in nodes_module._session_cache
