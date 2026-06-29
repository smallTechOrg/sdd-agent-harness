"""Pydantic request/response models for the analysis API contract."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SchemaColumn(BaseModel):
    name: str
    type: str


class ColumnProfile(BaseModel):
    """Per-column profile entry (Phase 2 — now populated)."""

    column: str
    type: str
    null_count: int | None = None
    distinct_count: int | None = None
    min: Any | None = None
    max: Any | None = None
    flags: list[str] = Field(default_factory=list)


class DatasetSummary(BaseModel):
    """POST /datasets response payload."""

    id: str
    name: str
    row_count: int
    schema_: list[SchemaColumn] = Field(serialization_alias="schema", alias="schema")
    # Phase 2 — now populated: list of per-column profile entries (or null).
    profile: list[ColumnProfile] | None = None

    model_config = {"populate_by_name": True}


class AskRequest(BaseModel):
    question: str


class ChartSpec(BaseModel):
    """Chart spec derived from the aggregate result shape (Phase 2)."""

    type: str  # "bar" | "line" | "scatter"
    x: str
    y: str
    series: str | None = None
    title: str


class SummaryColumn(BaseModel):
    name: str
    type: str  # "number" | "text"
    align: str  # "right" | "left"


class SummaryTable(BaseModel):
    columns: list[SummaryColumn]
    rows: list[list[Any]]


class AskResponse(BaseModel):
    """POST /datasets/{id}/ask response payload (the core contract)."""

    run_id: str
    dataset_id: str
    status: str
    question: str
    answer: str | None = None
    sql: str | None = None
    result: list[dict] | None = None
    flagged: bool = False
    error: str | None = None

    # Phase 2 — now populated (null when not applicable / on failure).
    chart: ChartSpec | None = None
    summary_table: SummaryTable | None = None
    followups: list[str] | None = None
    # tokens stays null until Phase 3.
    tokens: Any | None = None
