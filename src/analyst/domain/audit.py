from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(description="When the execution was attempted")
    session_id: str = Field(description="Session that initiated the query")
    source_question: str = Field(description="The original natural-language question")
    sql: str = Field(description="The SQL statement that was executed")
    row_count: int = Field(default=0, description="Number of rows returned")
    status: str = Field(default="success", description="success or error")
    error_message: Optional[str] = Field(default=None, description="Error detail if status is error")
