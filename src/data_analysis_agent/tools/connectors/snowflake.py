"""Snowflake database connector (BETA).

Introspects via ``information_schema`` and, for querying, **loads** each table (capped) into a
DuckDB-registered DataFrame (DuckDB has no native Snowflake scanner). ``snowflake-connector-python`` is
imported lazily — install it (``pip install snowflake-connector-python``) to use this type. The raw URI
(with the password) is read only here, at connect time; errors are credential-sanitized.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from data_analysis_agent.tools.connectors.base import BaseConnector, DatasetConnectionError
from data_analysis_agent.tools.mcp.server import DEFAULT_MAX_ROWS, build_server, new_connection, register_dataframe_view

_LOAD_LIMIT = 2000  # rows loaded per table for the query path (BETA)


class SnowflakeConnector(BaseConnector):
    """Serves a `snowflake` database. URI: ``snowflake://user:pw@account/DB/SCHEMA?warehouse=WH``."""

    def _connect(self):
        try:
            import snowflake.connector as sf
        except ImportError:
            raise DatasetConnectionError(
                "Snowflake support requires 'snowflake-connector-python' (pip install snowflake-connector-python)."
            )
        p = urlsplit(self._uri.raw())
        params = parse_qs(p.query)
        path = [x for x in (p.path or "").split("/") if x]
        try:
            return sf.connect(
                account=p.hostname, user=p.username, password=p.password,
                database=path[0] if path else None,
                schema=path[1] if len(path) > 1 else None,
                warehouse=(params.get("warehouse") or [None])[0],
                login_timeout=8, network_timeout=8,
            )
        except DatasetConnectionError:
            raise
        except Exception as exc:
            raise DatasetConnectionError(f"Could not connect to {self._uri.display()}: {self._sanitize(exc)}")

    def connection_check(self) -> None:
        """Connect + ``SELECT 1``; raise a sanitized error on failure."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()

    def discover_tables(self) -> list[dict]:
        """Introspect ``information_schema`` for tables/columns in the current schema."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = CURRENT_SCHEMA() ORDER BY table_name")
            names = [r[0] for r in cur.fetchall()]
            tables: list[dict] = []
            for name in names:
                cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                            "WHERE table_name = %s AND table_schema = CURRENT_SCHEMA() ORDER BY ordinal_position",
                            (name,))
                cols = cur.fetchall()
                tables.append({
                    "table_name": name,
                    "column_names": [c[0] for c in cols],
                    "schema": [{"name": c[0], "dtype": c[1], "nullable": c[2] == "YES"} for c in cols],
                    "row_count": None,
                })
            return tables
        finally:
            conn.close()

    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS):
        """Load each **given** table (capped) into a DuckDB-registered DataFrame (no introspect)."""
        import pandas as pd
        conn = self._connect()
        duck = new_connection()
        try:
            cur = conn.cursor()
            for name in table_names:
                cur.execute(f'SELECT * FROM "{name}" LIMIT {_LOAD_LIMIT}')
                if hasattr(cur, "fetch_pandas_all"):
                    df = cur.fetch_pandas_all()
                else:
                    df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
                register_dataframe_view(duck, name, df)
            return build_server(self._server.get("name") or "database", duck,
                                [{"table_name": n} for n in table_names], max_rows)
        finally:
            conn.close()

    def _sanitize(self, exc: Exception) -> str:
        msg = str(exc).replace(self._uri.raw(), self._uri.display())
        password = urlsplit(self._uri.raw()).password
        if password:
            msg = msg.replace(password, "***")
        return msg
