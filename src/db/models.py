from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class Dataset(Base):
    """An uploaded CSV/Excel file and its inferred schema.

    Holds a path reference and the schema JSON only — never the raw rows.
    Raw rows live solely as files under ./data/uploads/.
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)  # "csv" | "xlsx"
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)  # LLM-safe, no rows
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class Conversation(Base):
    """A chat thread scoped to one dataset."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class Message(Base):
    """One turn in a conversation. Assistant messages may carry a chart spec."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        Text, ForeignKey("conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chart_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # ChartSpec JSON
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
