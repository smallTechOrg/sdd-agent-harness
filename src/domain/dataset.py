"""Pydantic request/response models for the datasets API surface (spec/api.md)."""
from typing import Any

from pydantic import BaseModel


class ColumnSchema(BaseModel):
    name: str
    type: str


class DatasetResponse(BaseModel):
    """Shape returned by POST /datasets and GET /datasets/{id}."""

    id: str
    name: str
    row_count: int
    columns: list[ColumnSchema]
    profile: dict[str, Any]
    status: str


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    """Shape returned by POST /datasets/{id}/ask (completed or failed)."""

    run_id: str
    status: str
    answer: str | None = None
    key_numbers: list[dict[str, Any]] = []
    chart: dict[str, Any] | None = None
    table: dict[str, Any] | None = None
    plan: str | None = None
    sql: str | None = None
    trace: list[dict[str, Any]] = []
    cost_usd: float = 0.0
    error_message: str | None = None


class DatasetSummary(BaseModel):
    """Lightweight summary returned by GET /datasets (sidebar list)."""

    id: str
    name: str
    row_count: int
    status: str
    question_count: int
    created_at: str | None = None


class RunRecord(AskResponse):
    """One persisted run returned by GET /datasets/{id}/runs.

    The live ``AskResponse`` shape plus the two fields history needs: the
    ``question`` (to label each run) and ``created_at`` (to order/timestamp it).
    Re-opened runs render through the existing ``AnswerPanel`` with no new
    component.
    """

    question: str
    created_at: str | None = None
