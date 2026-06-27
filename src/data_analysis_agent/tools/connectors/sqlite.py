"""SQLite database connector: a single ``.db`` file addressed by a ``sqlite:///path`` URI.

Introspection uses the stdlib ``sqlite3``; the query path uses DuckDB's ``sqlite_scanner`` (``ATTACH …
(TYPE sqlite)`` + one view per table), so the SELECT-only guard, row cap, and within-database JOINs are
shared with the other connectors. We never drop the user's tables.
"""
from __future__ import annotations

import sqlite3

from data_analysis_agent.tools.connectors.base import BaseConnector, DatasetConnectionError
from data_analysis_agent.tools.mcp.server import DEFAULT_MAX_ROWS, build_server, new_connection


class SQLiteConnector(BaseConnector):
    """Serves a `sqlite` database (a ``.db`` file); inspects it live via ``sqlite3``."""

    def __init__(self, server: dict) -> None:
        super().__init__(server)
        self._path = self._file_path(server.get("uri") or "")

    @staticmethod
    def _file_path(uri: str) -> str:
        from sqlalchemy.engine import make_url
        try:
            return make_url(uri).database or ""
        except Exception:
            return uri.replace("sqlite://", "", 1).lstrip("/")

    def connection_check(self) -> None:
        """Open the file and run ``SELECT 1``; raise a sanitized error on failure."""
        try:
            conn = sqlite3.connect(self._path)
            conn.execute("SELECT 1")
            conn.close()
        except Exception as exc:
            raise DatasetConnectionError(f"Could not open SQLite database {self._uri.display()}: {exc}")

    def discover_tables(self) -> list[dict]:
        """Introspect ``sqlite_master`` + ``PRAGMA table_info`` for user tables (empty on failure)."""
        try:
            conn = sqlite3.connect(self._path)
            try:
                names = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name")]
                tables: list[dict] = []
                for name in names:
                    cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()  # (cid,name,type,notnull,dflt,pk)
                    row_count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                    tables.append({
                        "table_name": name,
                        "column_names": [c[1] for c in cols],
                        "schema": [{"name": c[1], "dtype": c[2] or "", "nullable": c[3] == 0} for c in cols],
                        "row_count": row_count,
                    })
                return tables
            finally:
                conn.close()
        except Exception as exc:
            raise DatasetConnectionError(f"Could not introspect {self._uri.display()}: {exc}")

    def discover_relationships(self) -> list[dict]:
        """Declared foreign keys (``PRAGMA foreign_key_list``) in the canonical FK-edge format."""
        rels: list[dict] = []
        try:
            conn = sqlite3.connect(self._path)
            try:
                names = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                for name in names:
                    for fk in conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall():
                        # (id, seq, table, from, to, on_update, on_delete, match)
                        rels.append({"from_table": name, "from_column": fk[3],
                                     "to_table": fk[2], "to_column": fk[4]})
            finally:
                conn.close()
        except Exception:
            return []
        return rels

    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS):
        """ATTACH the SQLite file in DuckDB and expose one read-only view per **given** table (no introspect)."""
        import duckdb

        conn = new_connection()
        try:
            conn.execute("INSTALL sqlite")
            conn.execute("LOAD sqlite")
            safe_path = self._path.replace("'", "''")
            conn.execute(f"ATTACH '{safe_path}' AS sqlitedb (TYPE sqlite, READ_ONLY)")
            for name in table_names:
                safe = name.replace('"', '""')
                conn.execute(f'CREATE VIEW "{safe}" AS SELECT * FROM sqlitedb."{safe}"')
        except duckdb.Error as exc:
            conn.close()
            raise DatasetConnectionError(f"Could not open {self._uri.display()}: {exc}")
        return build_server(self._server.get("name") or "database", conn,
                            [{"table_name": n} for n in table_names], max_rows)
