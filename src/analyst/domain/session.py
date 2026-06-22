from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ColumnDef(BaseModel):
    name: str = Field(description="Column name as it appears in the file header")
    type: str = Field(description="Inferred data type (text, integer, float, boolean, date, datetime)")


class DatasetMeta(BaseModel):
    dataset_id: str = Field(description="Unique identifier for this dataset within the session")
    name: str = Field(description="Logical table name (normalised)")
    original_filename: str = Field(description="The file name as uploaded by the user")
    format: str = Field(description="File format: csv or json")
    columns: list[ColumnDef] = Field(description="Inferred schema columns")
    row_count: int = Field(description="Total number of data rows in the file")
    size_bytes: int = Field(description="Size of the stored file in bytes")
    file_path: str = Field(description="Absolute path to the stored file")
    uploaded_at: datetime = Field(description="When the file was stored")


class ConversationTurn(BaseModel):
    turn_id: str = Field(description="Unique identifier for this turn")
    role: str = Field(description="user or assistant")
    content: str = Field(description="Message content")
    sql: Optional[str] = Field(default=None, description="SQL generated for this turn")
    result_summary: Optional[str] = Field(default=None, description="Brief result summary")
    timestamp: datetime = Field(description="When this turn was created")


class Session(BaseModel):
    session_id: str = Field(description="Primary key; value of the session cookie")
    created_at: datetime = Field(description="When the session was first created")
    last_active_at: datetime = Field(description="Updated on every API request")
    datasets: list[DatasetMeta] = Field(default_factory=list, description="Datasets in this session")
    conversation: list[ConversationTurn] = Field(
        default_factory=list, description="Ordered conversation history"
    )
