"""Thin tool wrapper: parquet path -> (profile, suggested_questions).

Convenience for the upload handler / graph: load the full frame, profile it, and
(optionally) ask for suggested questions in one call. The privacy boundary is
preserved — only the computed profile is passed to ``suggest_questions``.
"""

from __future__ import annotations

from datasets.profiler import profile_dataframe, suggest_questions
from datasets.store import load_dataframe


def profile_parquet(parquet_path: str, *, with_suggestions: bool = True) -> dict:
    """Profile a stored Parquet dataset.

    Returns ``{profile, suggested_questions}``. The DataFrame is loaded full (no
    sampling); only the resulting profile metadata is sent to the LLM for
    suggestions.
    """
    df = load_dataframe(parquet_path)
    profile = profile_dataframe(df)
    suggestions = suggest_questions(profile) if with_suggestions else []
    return {"profile": profile, "suggested_questions": suggestions}
