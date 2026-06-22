from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ColumnSchema(BaseModel):
    name: str
    type: str


class ResultTable(BaseModel):
    """A rendered query result: column names plus row tuples."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class Session(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class Dataset(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    session_id: int
    name: str
    source_filename: str
    file_format: Literal["csv", "parquet"]
    duckdb_table: str
    row_count: int
    schema_json: list[ColumnSchema] = Field(default_factory=list)
    sample_rows_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: Literal["user", "assistant"]
    content: str
    generated_sql: str | None = None
    result_table_json: dict[str, Any] | None = None
    created_at: datetime


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    nl_prompt: str | None = None
    generated_sql: str | None = None
    row_count: int | None = None
    duration_ms: int
    status: Literal["success", "error"]
    error_message: str | None = None
    created_at: datetime
