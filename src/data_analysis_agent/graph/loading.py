from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import structlog

from data_analysis_agent.graph.data_cache import store_connection
from data_analysis_agent.graph.sql_aggregates import register_sql_functions
from data_analysis_agent.tools.table_naming import sql_table_name

log = structlog.get_logger()


def open_session_db(run_id: str) -> sqlite3.Connection:
    """Create the run's in-memory SQLite DB, register aggregates, and cache it.

    Args:
        run_id: The pipeline run id the connection is cached under.

    Returns:
        A fresh in-memory SQLite connection with statistical aggregates registered.
    """
    conn = sqlite3.connect(":memory:")
    register_sql_functions(conn)
    store_connection(run_id, conn)
    return conn


def load_sources_into_sqlite(conn: sqlite3.Connection, sources: list[dict]) -> tuple[list[str], int]:
    """Load every data source into its own table in the in-memory database.

    Each source is read from Parquet (preferred) or CSV and written to a table
    named after the source. Column names are namespaced as ``table.column``.

    Args:
        conn: The in-memory SQLite connection to populate.
        sources: Serialised data source dicts from the tool registry.

    Returns:
        A ``(column_names, total_row_count)`` tuple across all loaded sources.
    """
    column_names: list[str] = []
    total_rows = 0
    for source in sources:
        frame = _read_source_frame(source)
        if frame is None:
            continue
        table = sql_table_name(source["name"])
        frame.to_sql(table, conn, index=False, if_exists="replace")
        column_names.extend(f"{table}.{col}" for col in frame.columns)
        total_rows += len(frame)
    return column_names, total_rows


def assign_table_names(tools: list[dict], sources: list[dict]) -> list[dict]:
    """Return tools with each ``csv_query`` config carrying its runtime table name.

    Args:
        tools: Serialised tool dicts from the registry.
        sources: Serialised data source dicts, used to resolve table names.

    Returns:
        A new list of tool dicts; ``csv_query`` tools gain a ``table_name`` config.
    """
    by_id = {s["id"]: s for s in sources}
    resolved: list[dict] = []
    for tool in tools:
        source = by_id.get(tool.get("data_source_id"))
        if tool["type"] == "csv_query" and source:
            table = sql_table_name(source["name"])
            tool = {**tool, "config": {**tool.get("config", {}), "table_name": table}}
        resolved.append(tool)
    return resolved


def _read_source_frame(source: dict) -> pd.DataFrame | None:
    """Read a data source into a DataFrame, preferring Parquet over raw CSV.

    Args:
        source: A serialised data source dict with ``parquet_path``/``file_path``.

    Returns:
        The loaded DataFrame, or ``None`` if no readable file is available.
    """
    parquet_path = source.get("parquet_path")
    if parquet_path and Path(parquet_path).exists():
        return pd.read_parquet(parquet_path)
    file_path = source.get("file_path")
    if file_path and Path(file_path).exists():
        return pd.read_csv(file_path)
    log.warning("load_data.no_file", ds_id=source.get("id"), name=source.get("name"))
    return None
