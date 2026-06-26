from __future__ import annotations

import warnings
from pydantic import BaseModel, Field
from typing import Any


class UploadResponse(BaseModel):
    session_id: str
    table_name: str
    row_count: int
    # Named "schema" in the API contract; suppress Pydantic shadow warning
    schema_: list[dict] = Field(default_factory=list, alias="schema")

    model_config = {"populate_by_name": True}


class QueryRequest(BaseModel):
    session_id: str
    question: str


class QueryResponse(BaseModel):
    query_run_id: str
    status: str
    sql: str | None = None
    chart_spec: Any | None = None
    insight: str | None = None
    error: str | None = None
