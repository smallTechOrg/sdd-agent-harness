import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Float, Text, TIMESTAMP, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    """Return a new random UUID string for use as a primary-key default."""
    return str(uuid4())


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DataSourceRow(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="csv")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_names_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    @property
    def column_names(self) -> list[str]:
        """Decode the JSON-encoded list of column names (empty list if unset)."""
        if self.column_names_json:
            return json.loads(self.column_names_json)
        return []

    @column_names.setter
    def column_names(self, value: list[str]) -> None:
        """Encode and store the list of column names as JSON."""
        self.column_names_json = json.dumps(value)

    @property
    def schema(self) -> list[dict]:
        """Column schema with dtype and nullability: [{name, dtype, nullable}]."""
        if self.schema_json:
            return json.loads(self.schema_json)
        return []


class ToolRow(Base):
    __tablename__ = "tools"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    data_source_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    @property
    def config(self) -> dict:
        """Decode the tool's JSON config blob into a dict (empty dict if unset)."""
        if self.config_json:
            return json.loads(self.config_json)
        return {}


class ToolCapabilityRow(Base):
    __tablename__ = "tool_capabilities"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    tool_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )

    @property
    def parameter_schema(self) -> dict:
        """Decode the capability's JSON parameter schema into a dict."""
        return json.loads(self.parameter_schema_json)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class SessionDataSourceRow(Base):
    __tablename__ = "session_data_sources"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    data_source_id: Mapped[str] = mapped_column(Text, primary_key=True)


class QueryRecordRow(Base):
    __tablename__ = "query_records"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    iteration_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_request_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    @property
    def query_history(self) -> list[dict]:
        """Decode the JSON-encoded tool-call trace into a list of dicts."""
        if self.query_history_json:
            return json.loads(self.query_history_json)
        return []


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    query_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )
