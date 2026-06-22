from datetime import datetime
from pydantic import BaseModel, Field
from uuid import uuid4


def _uid() -> str:
    """Return a new random UUID as a string, for use as a default primary key."""
    return str(uuid4())


class DataSource(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    type: str = "csv"
    description: str | None = None
    file_path: str | None = None
    row_count: int | None = None
    column_names: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class Tool(BaseModel):
    id: str = Field(default_factory=_uid)
    data_source_id: str
    name: str
    type: str
    description: str
    config: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ToolCapability(BaseModel):
    id: str = Field(default_factory=_uid)
    tool_id: str
    name: str
    description: str
    parameter_schema: dict = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str | None = None
    data_source_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueryRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    session_id: str
    question: str
    answer: str | None = None
    status: str = "pending"
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AgentRunRecord(BaseModel):
    id: str = Field(default_factory=_uid)
    query_record_id: str
    status: str = "pending"
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
