"""Internal Parquet database connector: a directory of Parquet files, one view (table) per file.

The connector owns its physical-table inspection — it scans `{datasets_dir}/{slug(name)}/*.parquet`
live. The app stores no table catalog.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import structlog

from data_analysis_agent.tools.connectors.base import BaseConnector, DatasetConnectionError
from data_analysis_agent.tools.mcp.server import (
    DEFAULT_MAX_ROWS,
    build_server,
    new_connection,
    register_parquet_view,
)

log = structlog.get_logger()


class ParquetConnector(BaseConnector):
    """Serves a `parquet` database: a directory of Parquet files keyed by the database name."""

    def _directory(self) -> Path:
        """The on-disk directory holding this database's Parquet files (`{datasets_dir}/{slug(name)}`)."""
        from data_analysis_agent.config.settings import get_settings
        from data_analysis_agent.tools.table_naming import sql_table_name
        return Path(get_settings().datasets_dir) / sql_table_name(self._server.get("name") or "")

    def connection_check(self) -> None:
        """Validate the directory is accessible and any present Parquet files are readable.

        A parquet database with **zero tables is valid** (e.g. just created, nothing uploaded yet), so a
        missing directory passes.
        """
        directory = self._directory()
        if not directory.exists():
            return  # empty database — no tables uploaded yet
        try:
            tables = self.discover_tables()
        except Exception as exc:
            raise DatasetConnectionError(f"Could not read the database directory: {exc}")
        for table in tables:
            path = table.get("parquet_path")
            try:
                conn = duckdb.connect(database=":memory:")
                conn.execute(f"SELECT * FROM read_parquet('{(path or '').replace(chr(39), chr(39) * 2)}') LIMIT 0")
                conn.close()
            except duckdb.Error as exc:
                raise DatasetConnectionError(
                    f"Dataset file unreadable for table '{table.get('table_name')}': {exc}"
                )

    def discover_tables(self) -> list[dict]:
        """Scan the directory and return one table dict per Parquet file (empty if none)."""
        directory = self._directory()
        if not directory.exists():
            return []
        tables: list[dict] = []
        for path in sorted(directory.glob("*.parquet")):
            pf = pq.ParquetFile(str(path))
            schema = pf.schema_arrow
            tables.append({
                "table_name": path.stem,
                "parquet_path": str(path.resolve()),
                "column_names": list(schema.names),
                "schema": [{"name": f.name, "dtype": str(f.type), "nullable": f.nullable} for f in schema],
                "row_count": pf.metadata.num_rows,
            })
        return tables

    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS):
        """Register one view per named Parquet file (path derived from the name) and build the server.

        No directory scan — the table set comes from the caller (resources/sync). A name whose file is
        gone (out-of-band deletion) is skipped so one stale row can't break the whole server.
        """
        directory = self._directory()
        conn = new_connection()
        registered: list[dict] = []
        for name in table_names:
            try:
                register_parquet_view(conn, name, str(directory / f"{name}.parquet"))
                registered.append({"table_name": name})
            except FileNotFoundError as exc:
                log.warning("parquet.view_missing", table=name, error=str(exc))
        return build_server(self._server.get("name") or "database", conn, registered, max_rows)

    def drop_table(self, table_name: str) -> None:
        """Delete a table's Parquet file from the directory (best-effort)."""
        (self._directory() / f"{table_name}.parquet").unlink(missing_ok=True)
