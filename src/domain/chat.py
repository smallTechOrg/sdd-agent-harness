"""Pydantic models for the chat endpoints.

Mirrors spec/api.md for `POST /chat` and `GET /conversations/{id}` exactly,
including the shared ChartSpec shape.
"""
from pydantic import BaseModel


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartSpec(BaseModel):
    type: str  # "bar" | "line" | "pie"
    title: str
    labels: list[str]
    series: list[ChartSeries]


class ChatRequest(BaseModel):
    dataset_id: str
    question: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    chart: ChartSpec | None = None


class ConversationMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    chart: ChartSpec | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    dataset_id: str
    messages: list[ConversationMessage]
