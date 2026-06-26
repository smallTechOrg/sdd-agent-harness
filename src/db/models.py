from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Text, TIMESTAMP, Integer, Float, JSON
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

    # Observability
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    guard_code: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class TurnRow(Base):
    """Session memory: one row per conversation turn (the wired memory flavour)."""
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)   # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )


class FactRow(Base):
    """Semantic memory facts (LABELLED SLOT — not on the green path)."""
    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    subject: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
