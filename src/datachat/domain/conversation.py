"""Domain models for conversations, messages, and agent runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ResultTable(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class ChartPoint(BaseModel):
    x: Any
    y: Any


class ChartSpec(BaseModel):
    type: str
    title: str
    x: str
    y: str
    data: list[ChartPoint]


class TraceStep(BaseModel):
    description: str
    action: str
    result: str
    is_error: bool


class MessageRead(BaseModel):
    id: str
    conversation_id: str
    run_id: str | None
    role: Literal["user", "assistant"]
    content: str
    result_table: ResultTable | None = None
    chart: ChartSpec | None = None
    trace: list[TraceStep] | None = None
    created_at: datetime


class ConversationCreate(BaseModel):
    dataset_id: str
    title: str | None = None


class ConversationRead(BaseModel):
    id: str
    dataset_id: str
    title: str | None
    created_at: datetime
    messages: list[MessageRead] = []


class QueryRequest(BaseModel):
    question: str


class RunRead(BaseModel):
    id: str
    conversation_id: str
    status: Literal["running", "completed", "failed"]
    iteration_count: int
    early_exit_reason: str | None
    tokens_input: int
    tokens_output: int
    estimated_cost_usd: float | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
