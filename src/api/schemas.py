"""API request/response models for the Pandora routes.

These live in the API layer (not ``src/domain/``, which the db-migration slice
owns) and describe only the request bodies and response payloads the routers
shape. DB models come from ``db.models`` and the typed profile from
``domain.DatasetProfile``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class AskRequest(BaseModel):
    """Body of ``POST /datasets/{id}/ask``."""

    question: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Response payloads (wrapped by ``ok(...)`` at the route)
# --------------------------------------------------------------------------- #
class DatasetResponse(BaseModel):
    """``POST /datasets`` and ``GET /datasets/{id}`` payload."""

    dataset_id: str
    filename: str
    row_count: int
    column_count: int
    profile: dict[str, Any]
    suggested_questions: list[str]
    status: str


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class QuestionResponse(BaseModel):
    """``GET /questions/{id}`` payload."""

    id: str
    dataset_id: str
    question: str
    code: str | None = None
    answer_text: str | None = None
    chart_spec: dict[str, Any] | None = None
    summary_table: dict[str, Any] | None = None
    usage: Usage
    status: str
    created_at: str | None = None


class CostTodayResponse(BaseModel):
    """``GET /cost/today`` payload."""

    date: str
    total_usd: float
    question_count: int
