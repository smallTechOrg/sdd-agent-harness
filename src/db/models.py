from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, Text, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Dataset(Base):
    """One uploaded file plus its computed profile.

    The Parquet on disk (`parquet_path`) is the canonical analysis data; this
    row is its metadata. `profile_json` holds the serialized ``DatasetProfile``
    — the only dataset information ever sent to the LLM.
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_questions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="ready")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )


class Question(Base):
    """One asked question and its full, revisitable record.

    Holds the generated code, the answer, the chart/table payloads, and the
    per-question token + cost accounting.
    """

    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datasets.id"), nullable=False, index=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    chart_spec_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_table_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=_now, onupdate=_now
    )
