from datetime import datetime
from typing import Any
from pydantic import BaseModel


class Session(BaseModel):
    session_id: str
    filename: str
    status: str
    row_count: int | None = None
    column_names: list[str] = []
    error_message: str | None = None
    created_at: datetime | None = None


class Message(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    reasoning_trace: list[dict[str, Any]] | None = None
    created_at: datetime | None = None


class Run(BaseModel):
    id: str
    session_id: str
    status: str
    tokens_input: int = 0
    tokens_output: int = 0
    error_message: str | None = None
    created_at: datetime | None = None
