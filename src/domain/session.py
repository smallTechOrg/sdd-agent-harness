from typing import Any
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    question: str


class AnalyzeResponse(BaseModel):
    run_id: str
    status: str
    question: str | None = None
    sql_query: str | None = None
    insight_json: dict[str, Any] | None = None
    insight_text: str | None = None
    output_text: str | None = None
    chart_specs: list[dict[str, Any]] | None = None
    error: str | None = None


class FileUploadResponse(BaseModel):
    table_name: str
    row_count: int
    columns: list[str]
    file_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    created_at: str | None = None


class UploadedFileInfo(BaseModel):
    file_id: str
    filename: str
    table_name: str
    row_count: int
    columns: list[str]
    created_at: str | None = None
