import os

import pandas as pd
import pytest

from datasets.profiler import profile_dataframe, suggest_questions


SENTINEL = "SECRET-SENTINEL-9f1c2b3a-do-not-leak"


def _gemini_key_present() -> bool:
    """True if a Gemini key is available via env or the project .env file."""
    if os.environ.get("AGENT_GEMINI_API_KEY"):
        return True
    try:
        from config.settings import Settings

        return bool(Settings().gemini_api_key)
    except Exception:
        return False


def _frame() -> pd.DataFrame:
    n = 20
    return pd.DataFrame(
        {
            # numeric column
            "amount": list(range(n)),
            # low-cardinality category -> example_labels, safe=True
            "region": (["North", "South", "East", "West"] * (n // 4)),
            # high-cardinality id column (unique per row) -> safe=False, no labels.
            # carries a sentinel value that must never appear in the profile.
            "user_id": [f"{SENTINEL}-{i}" for i in range(n)],
            # >30% missing column -> high_missing flag
            "notes": [("x" if i % 2 == 0 else None) if i < n // 2 else None
                      for i in range(n)],
            # constant column
            "source": ["import"] * n,
        }
    )


def _col(profile: dict, name: str) -> dict:
    return next(c for c in profile["columns"] if c["name"] == name)


def test_profile_shape_top_level():
    profile = profile_dataframe(_frame())
    assert profile["row_count"] == 20
    assert profile["column_count"] == 5
    assert isinstance(profile["columns"], list)
    for key in (
        "high_missing_columns",
        "constant_columns",
        "duplicate_row_count",
        "mixed_type_columns",
    ):
        assert key in profile


def test_numeric_column_has_stats():
    col = _col(profile_dataframe(_frame()), "amount")
    assert col["dtype"] == "integer"
    assert col["min"] == 0
    assert col["max"] == 19
    assert col["mean"] == pytest.approx(9.5)
    assert col["safe_to_sample_labels"] is False
    assert col["example_labels"] == []


def test_low_cardinality_category_exposes_labels():
    col = _col(profile_dataframe(_frame()), "region")
    assert col["dtype"] == "string"
    assert col["safe_to_sample_labels"] is True
    assert set(col["example_labels"]) == {"North", "South", "East", "West"}
    assert col["distinct_count"] == 4


def test_high_cardinality_column_leaks_no_values():
    profile = profile_dataframe(_frame())
    col = _col(profile, "user_id")
    assert col["safe_to_sample_labels"] is False
    assert col["example_labels"] == []
    # PRIVACY: the sentinel must not appear anywhere in the serialised profile.
    import json

    assert SENTINEL not in json.dumps(profile, default=str)


def test_high_missing_and_constant_flags():
    profile = profile_dataframe(_frame())
    assert "notes" in profile["high_missing_columns"]
    assert "source" in profile["constant_columns"]


def test_max_category_labels_cap(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_CATEGORY_LABELS", "3")
    df = pd.DataFrame({"cat": [f"c{i % 6}" for i in range(30)]})
    col = _col(profile_dataframe(df), "cat")
    assert col["safe_to_sample_labels"] is True
    assert len(col["example_labels"]) == 3


def test_suggest_questions_fallback_on_llm_error(monkeypatch):
    """When the LLM call raises, the upload still gets fallback questions.

    Force ``LLMClient`` construction to raise so we deterministically exercise
    the graceful-degradation path (independent of whether a real key is set).
    """
    import llm.client as client_mod

    def _boom(*_a, **_k):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr(client_mod, "LLMClient", _boom)

    profile = profile_dataframe(_frame())
    questions = suggest_questions(profile)

    assert 1 <= len(questions) <= 3
    assert all(isinstance(q, str) and q for q in questions)
    # fallback questions are derived from real column names / generic-but-relevant
    assert any(
        "amount" in q or "region" in q or "dataset" in q.lower()
        for q in questions
    )


def test_suggest_questions_parses_str_and_text_object(monkeypatch):
    """Works whether call_model returns a plain str or an object with .text."""
    import llm.client as client_mod

    class _Resp:
        text = '["What is the average amount by region?", "How many rows per region?"]'

    class _FakeClient:
        def call_model(self, prompt, *, system=None):
            # PRIVACY guard: only profile metadata is ever passed, never raw rows.
            assert SENTINEL not in prompt
            return _Resp()

    monkeypatch.setattr(client_mod, "LLMClient", lambda: _FakeClient())

    profile = profile_dataframe(_frame())
    questions = suggest_questions(profile)
    assert questions == [
        "What is the average amount by region?",
        "How many rows per region?",
    ]


@pytest.mark.skipif(
    not _gemini_key_present(),
    reason="real-key test: requires AGENT_GEMINI_API_KEY (env or .env)",
)
def test_suggest_questions_real_gemini():
    profile = profile_dataframe(_frame())
    questions = suggest_questions(profile)
    assert 2 <= len(questions) <= 3
    assert all(isinstance(q, str) and q.strip() for q in questions)
