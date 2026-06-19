"""Domain entities — extend the SAME Base as runs/messages/spans (harness/patterns/persistence.md).

v1 feature set: datasets + data_tables (uploaded-file metadata), charts (persisted Vega-Lite specs per
run), and conversations / conversation_turns (multi-turn threads). The tabular data itself lives in a
per-dataset DuckDB file (agent/duck.py), not in these tables.
"""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, _now, _uuid


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


class Conversation(Base):
    """A multi-turn thread bound to a dataset; runs link in via conversation_turns."""
    __tablename__ = "conversations"
    id:         Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True, index=True)
    title:      Mapped[str] = mapped_column(String, default="New conversation")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ConversationTurn(Base):
    """Links one run into a conversation, in order — the thread the next turn reconstructs from."""
    __tablename__ = "conversation_turns"
    id:              Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    run_id:          Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    idx:             Mapped[int] = mapped_column(Integer, default=0)
    created_at:      Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Chart(Base):
    """A persisted Vega-Lite spec (data embedded) produced by a run, rendered by the UI."""
    __tablename__ = "charts"
    id:         Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id:     Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    title:      Mapped[str] = mapped_column(String, default="")
    spec:       Mapped[dict] = mapped_column(JSON, default=dict)   # full Vega-Lite v5 spec incl. data.values
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
