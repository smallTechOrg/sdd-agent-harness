"""Full-data profiling + privacy-bounded question suggestions.

The profiler computes a ``DatasetProfile`` over the *entire* DataFrame (never a
sample). It is the single source of the only dataset information that ever leaves
the machine: per the privacy boundary (architecture.md), the LLM sees schema and
bounded metadata only — never a raw row.

``suggest_questions`` is the LLM seam. The ONLY thing handed to the model is the
profile dict (schema/metadata, incl. bounded example labels for low-cardinality
columns). The DataFrame and any raw column are never in scope here.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
from pandas.api import types as ptypes

# Privacy bounds (architecture.md "Category-label nuance").
_DEFAULT_MAX_CATEGORY_LABELS = 10
# Only string columns at or below this distinct count may expose example labels.
_LABEL_DISTINCT_CEILING = 50
# A column whose distinct count is this fraction (or more) of its non-null rows
# is effectively unique-per-row — an id/email/free-text column — and exposes NO
# labels regardless of the absolute distinct count (privacy: never leak ids on a
# small dataset where distinct happens to fall under the ceiling).
_UNIQUE_RATIO_CEILING = 0.9
# Below this many non-null rows the unique-ratio heuristic is unreliable, so a
# genuinely small enumerated column (e.g. 4 regions in 6 rows) is still allowed.
_UNIQUE_RATIO_MIN_ROWS = 12
# Quality-flag threshold.
_HIGH_MISSING_PCT = 30.0

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "suggest.md"


def _max_category_labels() -> int:
    """Read ``AGENT_MAX_CATEGORY_LABELS`` from settings/env, defaulting to 10.

    Read defensively so this slice doesn't couple to the settings module's exact
    fields (another slice owns settings.py).
    """
    try:
        from config.settings import get_settings

        val = getattr(get_settings(), "max_category_labels", None)
        if val is not None:
            return int(val)
    except Exception:
        pass
    raw = os.environ.get("AGENT_MAX_CATEGORY_LABELS")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return _DEFAULT_MAX_CATEGORY_LABELS


def _dtype_name(series: pd.Series) -> str:
    """Coarse, LLM-friendly dtype label."""
    if ptypes.is_bool_dtype(series):
        return "boolean"
    if ptypes.is_integer_dtype(series):
        return "integer"
    if ptypes.is_float_dtype(series):
        return "float"
    if ptypes.is_datetime64_any_dtype(series):
        return "datetime"
    return "string"


def _is_mixed_type(series: pd.Series) -> bool:
    """True when an object column holds more than one python scalar type."""
    if not ptypes.is_object_dtype(series):
        return False
    seen: set[str] = set()
    for v in series.dropna():
        seen.add(type(v).__name__)
        if len(seen) > 1:
            return True
    return False


def profile_dataframe(df: pd.DataFrame) -> dict:
    """Compute the full-data ``DatasetProfile`` dict.

    The returned dict validates as the ``DatasetProfile`` domain model when that
    model is present; either way it conforms to the shape documented in
    architecture.md so downstream slices (graph node, API) can rely on it.
    """
    max_labels = _max_category_labels()
    n_rows = int(df.shape[0])

    columns: list[dict] = []
    high_missing_columns: list[str] = []
    constant_columns: list[str] = []
    mixed_type_columns: list[str] = []

    for name in df.columns:
        series = df[name]
        col_name = str(name)
        dtype = _dtype_name(series)
        null_count = int(series.isna().sum())
        missing_pct = round((null_count / n_rows * 100.0), 2) if n_rows else 0.0
        distinct_count = int(series.nunique(dropna=True))

        col: dict = {
            "name": col_name,
            "dtype": dtype,
            "null_count": null_count,
            "missing_pct": missing_pct,
            "distinct_count": distinct_count,
            "min": None,
            "max": None,
            "mean": None,
            "safe_to_sample_labels": False,
            "example_labels": [],
        }

        if dtype in ("integer", "float", "boolean") and null_count < n_rows:
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().any():
                col["min"] = _py(numeric.min())
                col["max"] = _py(numeric.max())
                col["mean"] = round(float(numeric.mean()), 4)
        elif dtype == "datetime" and null_count < n_rows:
            col["min"] = _py_date(series.min())
            col["max"] = _py_date(series.max())
        elif dtype == "string":
            # PRIVACY: only low-cardinality, non-id string columns expose labels.
            # High-cardinality columns (names, emails, ids, free text) expose
            # count/missing only — never an example value. A column whose values
            # are (nearly) unique per row is treated as id-like and stays unsafe
            # even when its absolute distinct count is under the ceiling.
            non_null = n_rows - null_count
            unique_ratio = (distinct_count / non_null) if non_null else 0.0
            looks_like_id = (
                non_null >= _UNIQUE_RATIO_MIN_ROWS
                and unique_ratio >= _UNIQUE_RATIO_CEILING
            )
            if 0 < distinct_count <= _LABEL_DISTINCT_CEILING and not looks_like_id:
                col["safe_to_sample_labels"] = True
                labels = (
                    series.dropna().astype(str).drop_duplicates().tolist()[:max_labels]
                )
                col["example_labels"] = labels

        # quality flags
        if missing_pct > _HIGH_MISSING_PCT:
            high_missing_columns.append(col_name)
        if n_rows > 0 and distinct_count <= 1:
            constant_columns.append(col_name)
        if _is_mixed_type(series):
            mixed_type_columns.append(col_name)

        columns.append(col)

    try:
        duplicate_row_count = int(df.duplicated().sum())
    except TypeError:
        # unhashable cell types (rare) — can't dedupe; report 0 rather than crash
        duplicate_row_count = 0

    return {
        "row_count": n_rows,
        "column_count": int(df.shape[1]),
        "columns": columns,
        "high_missing_columns": high_missing_columns,
        "constant_columns": constant_columns,
        "duplicate_row_count": duplicate_row_count,
        "mixed_type_columns": mixed_type_columns,
    }


def _py(value):
    """Coerce a numpy scalar to a JSON-friendly python scalar."""
    if value is None or pd.isna(value):
        return None
    try:
        return value.item()  # numpy scalar -> python scalar
    except AttributeError:
        return value


def _py_date(value):
    if value is None or pd.isna(value):
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


# --------------------------------------------------------------------------- #
# Suggested questions (the LLM seam)
# --------------------------------------------------------------------------- #

def _load_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "You suggest 2-3 short, plain-language questions a user could ask "
            "about a dataset, given only its schema and metadata. Return a JSON "
            "array of strings."
        )


def _fallback_questions(profile: dict) -> list[str]:
    """Generic-but-relevant questions derived from column names (no LLM)."""
    cols = [c.get("name") for c in profile.get("columns", []) if c.get("name")]
    numeric = [
        c["name"]
        for c in profile.get("columns", [])
        if c.get("dtype") in ("integer", "float")
    ]
    categorical = [
        c["name"]
        for c in profile.get("columns", [])
        if c.get("safe_to_sample_labels")
    ]

    questions: list[str] = []
    if numeric and categorical:
        questions.append(
            f"What is the average {numeric[0]} by {categorical[0]}?"
        )
    elif numeric:
        questions.append(f"What is the total {numeric[0]}?")
    if categorical:
        questions.append(f"How many rows are there for each {categorical[0]}?")
    if cols:
        questions.append("How many rows and columns does this dataset have?")

    # de-dup while preserving order; cap at 3
    seen: set[str] = set()
    out: list[str] = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:3] or ["What does this dataset contain?"]


def _coerce_text(response) -> str:
    """Accept either a plain string or an object exposing ``.text``.

    The cost-accounting slice may change ``call_model`` to return a richer
    object; handle both so we work whether or not that has landed.
    """
    if isinstance(response, str):
        return response
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text
    return str(response)


def _parse_questions(text: str) -> list[str]:
    """Extract 2-3 non-empty question strings from an LLM response."""
    text = (text or "").strip()
    if not text:
        return []

    # try JSON array first (possibly fenced)
    candidate = text
    if "```" in candidate:
        # strip a ```json ... ``` fence
        parts = candidate.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[len("json"):].strip()
            if part.startswith("[") and part.endswith("]"):
                candidate = part
                break

    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            items = [str(q).strip() for q in data if str(q).strip()]
            if items:
                return items[:3]
    except (json.JSONDecodeError, ValueError):
        pass

    # fall back to line parsing (numbered/bulleted lists)
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*0123456789.) ").strip()
        if line:
            lines.append(line)
    return lines[:3]


def suggest_questions(profile: dict) -> list[str]:
    """Ask Gemini for 2-3 plain-language questions about THIS dataset.

    PRIVACY: the only thing sent to the model is ``profile`` (schema/metadata) —
    serialised to JSON. No DataFrame, no raw column, no row ever reaches here.
    On any LLM error, degrade to generic-but-relevant fallback questions derived
    from column names so the upload never fails on the suggestion step.
    """
    # The single payload that crosses the LLM boundary — profile metadata only.
    payload = json.dumps(profile, default=str)
    system = _load_prompt()

    try:
        from llm.client import LLMClient

        response = LLMClient().call_model(payload, system=system)
        questions = _parse_questions(_coerce_text(response))
        if questions:
            return questions[:3]
    except Exception:
        # any provider/parse error → graceful fallback (upload still succeeds)
        pass

    return _fallback_questions(profile)
