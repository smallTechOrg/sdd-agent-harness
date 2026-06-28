from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """API/serialization view of a ``messages`` row — one analysis run.

    ``key_numbers`` and ``result_table`` are the parsed JSON payloads (the row
    stores them as JSON strings in ``key_numbers_json`` / ``result_table_json``);
    callers parse/serialize at the boundary.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    question: str
    plan: str | None = None
    generated_code: str | None = None
    answer: str | None = None
    key_numbers: dict[str, Any] = Field(default_factory=dict)
    result_table: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    status: str = "running"
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
