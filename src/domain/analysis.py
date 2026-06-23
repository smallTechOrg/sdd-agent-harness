"""Pydantic models for the data-analyst API (spec/api.md shapes)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ColumnDescriptor(BaseModel):
    name: str
    type: str


class DatasetOut(BaseModel):
    """Response payload for POST /datasets and items in GET /datasets."""

    id: str
    name: str
    session_id: str | None = None
    row_count: int
    schema_: list[ColumnDescriptor] = Field(default_factory=list, alias="schema")
    sample_rows: list[list[Any]] = Field(default_factory=list)
    created_at: str | None = None

    model_config = {"populate_by_name": True}


class AskRequest(BaseModel):
    dataset_id: str
    question: str
    session_id: str | None = None


class AskResponse(BaseModel):
    run_id: str
    narrative: str | None = None
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: int = 0
    status: str


class AuditEntryOut(BaseModel):
    id: str
    dataset_id: str | None = None
    nl_question: str
    generated_sql: str | None = None
    row_count: int | None = None
    duration_ms: int | None = None
    status: str
    error_message: str | None = None
    created_at: str | None = None
