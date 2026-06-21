"""Domain entities — extend the SAME Base as runs/messages/spans (harness/patterns/persistence.md).

Phase 1: datasets + data_tables (metadata for the user's uploaded files). The tabular data itself lives in
a per-dataset DuckDB file (agent/duck.py), not in these tables. charts (Phase 2) and conversations /
conversation_turns (Phase 3) join here later.
"""
import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, _now, _uuid


class Thread(Base):
    """A conversation session tied to one dataset."""
    __tablename__ = "threads"
    id:                   Mapped[str] = mapped_column(String, primary_key=True)  # = thread_id from client
    dataset_id:           Mapped[str | None] = mapped_column(String, nullable=True)
    title:                Mapped[str] = mapped_column(String, default="")
    total_input_tokens:   Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens:  Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd:       Mapped[float] = mapped_column(Float, default=0.0)
    run_count:            Mapped[int] = mapped_column(Integer, default=0)
    created_at:           Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_active_at:       Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Dataset(Base):
    __tablename__ = "datasets"
    id:         Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name:       Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DataTable(Base):
    """One uploaded file → one queryable DuckDB table within a dataset."""
    __tablename__ = "data_tables"
    id:         Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    table_name: Mapped[str] = mapped_column(String)            # the DuckDB table name (sanitized)
    filename:   Mapped[str] = mapped_column(String)            # original upload filename
    n_rows:     Mapped[int] = mapped_column(Integer, default=0)
    n_cols:     Mapped[int] = mapped_column(Integer, default=0)
    columns:    Mapped[list] = mapped_column(JSON, default=list)  # [{"name": ..., "type": ...}, ...]
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
