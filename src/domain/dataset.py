"""Domain models that cross the privacy boundary.

The ``DatasetProfile`` is the typed object the profiler slice fills and the
graph code-gen node reads. It is the **only** dataset information ever sent to
the LLM: schema, per-column metadata/statistics, and dataset-level quality
flags — never raw rows. Example labels are exposed *only* for low-cardinality
columns the profiler has tagged ``safe_to_sample_labels`` (bounded by
``MAX_CATEGORY_LABELS``), per architecture.md "Privacy Boundary".
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    """Per-column schema + statistics. No raw row values cross here except a
    bounded set of category labels for columns flagged ``safe_to_sample_labels``.
    """

    name: str
    dtype: str
    null_count: int = 0
    missing_pct: float = 0.0

    # Numeric stats (None for non-numeric columns).
    min: float | None = None
    max: float | None = None
    mean: float | None = None

    # Date/datetime range (ISO strings; None for non-temporal columns).
    date_min: str | None = None
    date_max: str | None = None

    distinct_count: int | None = None

    # Category-label nuance: labels are exposed only for safe, low-cardinality
    # columns. High-cardinality columns (names, emails, IDs, free text) get
    # only count/missing — never example values.
    safe_to_sample_labels: bool = False
    example_labels: list[str] = Field(default_factory=list)


class DatasetProfile(BaseModel):
    """The full typed profile persisted on the ``datasets`` row and sent to the
    LLM in place of any raw data.
    """

    row_count: int = 0
    column_count: int = 0
    columns: list[ColumnProfile] = Field(default_factory=list)

    # Dataset-level data-quality flags.
    high_missing_columns: list[str] = Field(default_factory=list)
    constant_columns: list[str] = Field(default_factory=list)
    mixed_type_columns: list[str] = Field(default_factory=list)
    duplicate_row_count: int = 0
