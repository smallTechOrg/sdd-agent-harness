"""``build_llm_context`` — the single privacy chokepoint for LLM input.

This is the ONLY path that assembles text sent to Gemini. It is built from the
bounded local profile (schema + per-column ranges/missing + at most
``AGENT_SAMPLE_ROWS`` sample rows), the user's question, and the trimmed
conversation history (last ``AGENT_HISTORY_TURNS`` turns). It NEVER reads the
full dataframe — the full data is touched only by the local pandas sandbox,
never serialized into a prompt.

The output is bounded regardless of how large the underlying file is: it depends
only on the column count and the sample-row cap that profiling already applied,
so a 6-row file and a 60k-row file produce contexts of comparable size.
"""

from __future__ import annotations

import json
from typing import Any

# Fallback config values matching spec/.env.example. Real values come from
# get_settings() when those fields exist; we read them defensively so this slice
# does not depend on the settings module having been extended yet.
_DEFAULT_SAMPLE_ROWS = 20
_DEFAULT_HISTORY_TURNS = 6


def _config(name: str, default: int) -> int:
    """Read an int agent-config value from settings, defensively.

    The settings module may not yet expose every agent knob (other slices own
    it); fall back to the spec default rather than coupling to it.
    """
    try:
        from config.settings import get_settings

        value = getattr(get_settings(), name, None)
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _format_columns(columns: list[dict[str, Any]]) -> str:
    """Render the per-column schema + profile as compact, bounded lines."""
    lines: list[str] = []
    for col in columns:
        name = col.get("name")
        dtype = col.get("dtype")
        parts = [f"- {name} ({dtype})"]
        if "missing" in col:
            parts.append(f"missing={col['missing']}")
        # Numeric columns carry min/max/mean; object columns carry distinct/sample_values.
        if col.get("min") is not None or col.get("max") is not None:
            parts.append(f"min={col.get('min')}")
            parts.append(f"max={col.get('max')}")
        if col.get("mean") is not None:
            parts.append(f"mean={col.get('mean')}")
        if "distinct" in col:
            parts.append(f"distinct={col['distinct']}")
        if col.get("sample_values"):
            parts.append(f"examples={col['sample_values']}")
        lines.append("  ".join(parts))
    return "\n".join(lines)


def _format_history(messages: list[dict[str, Any]], turns: int) -> str:
    """Render the last ``turns`` conversation turns as role: content lines.

    Only the prior question + answer text is included — never any data. The
    history is trimmed to the most-recent ``turns`` entries.
    """
    if not messages:
        return ""
    trimmed = messages[-turns:] if turns > 0 else []
    lines: list[str] = []
    for turn in trimmed:
        role = turn.get("role", "user")
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_llm_context(
    profile: dict[str, Any],
    question: str,
    history: list[dict[str, Any]] | None,
) -> str:
    """Assemble the bounded LLM context string from local-only signals.

    Includes the schema (column names + dtypes), per-column ranges/missing,
    up to ``AGENT_SAMPLE_ROWS`` sample rows, the trimmed conversation history
    (last ``AGENT_HISTORY_TURNS`` turns), and the question. NEVER the full
    dataframe. The output size is bounded by the sample-row cap and the column
    count, regardless of file size.
    """
    sample_cap = _config("sample_rows", _DEFAULT_SAMPLE_ROWS)
    history_turns = _config("history_turns", _DEFAULT_HISTORY_TURNS)

    profile = profile or {}
    columns = profile.get("columns", []) or []
    row_count = profile.get("row_count")
    # Defensively re-cap the sample rows here too, so a profile built with a
    # larger cap can never leak more than the configured bound into a prompt.
    sample_rows = (profile.get("sample_rows", []) or [])[:sample_cap]

    sections: list[str] = []

    if row_count is not None:
        sections.append(f"DATASET: {row_count} total rows, {len(columns)} columns.")
    else:
        sections.append(f"DATASET: {len(columns)} columns.")

    sections.append("SCHEMA (column name, dtype, and profile):\n" + _format_columns(columns))

    if sample_rows:
        sections.append(
            f"SAMPLE ROWS (first {len(sample_rows)} of {row_count if row_count is not None else 'many'} "
            "— the full data is NOT shown and is analyzed locally):\n"
            + json.dumps(sample_rows, ensure_ascii=False)
        )

    history_text = _format_history(history or [], history_turns)
    if history_text:
        sections.append("RECENT CONVERSATION:\n" + history_text)

    sections.append("QUESTION:\n" + (question or "").strip())

    return "\n\n".join(sections)
