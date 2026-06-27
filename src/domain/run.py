from typing import Any
from pydantic import BaseModel


class RunRequest(BaseModel):
    input_text: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    question: str | None = None
    sql_query: str | None = None
    insight_json: dict[str, Any] | None = None
    insight_text: str | None = None
    output_text: str | None = None
    chart_specs: list[dict[str, Any]] | None = None
    error: str | None = None
    created_at: str | None = None
