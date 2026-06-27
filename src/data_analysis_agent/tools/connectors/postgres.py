"""External PostgreSQL dataset connector (BETA, flag-gated).

Two independent paths:
- connection_check / discover_tables via **psycopg2** (a real connect + ``SELECT 1`` + an
  ``information_schema`` introspection), each wrapped in a hard wall-clock timeout because
  ``psycopg2``'s own ``connect_timeout`` does not cover every stall.
- the query path via DuckDB ``ATTACH … (TYPE postgres, READ_ONLY)`` + one view per table, so the
  SELECT-only guard, row cap, and within-dataset JOINs are shared with parquet datasets.

The raw URI (with the password) is read only here, at connect time. Every error surfaced to the
caller is sanitized through ``DatasetURI.display()`` so credentials never leak.
"""
from __future__ import annotations

import concurrent.futures
from urllib.parse import urlsplit

from data_analysis_agent.tools.connectors.base import BaseConnector, DatasetConnectionError
from data_analysis_agent.tools.mcp.server import DEFAULT_MAX_ROWS, build_server, new_connection

_CONNECT_TIMEOUT_SECONDS = 8  # hard wall-clock cap around the whole connect/introspect


class PostgresConnector(BaseConnector):
    """Serves an external `postgresql` database; introspects its tables live via psycopg2."""

    def connection_check(self) -> None:
        """Connect + ``SELECT 1`` within a hard timeout; raise a sanitized error on any failure."""
        def probe() -> None:
            import psycopg2
            conn = psycopg2.connect(self._uri.raw(), connect_timeout=5)
            try:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
            finally:
                conn.close()

        self._with_timeout(probe, "connect to")

    def discover_tables(self) -> list[dict]:
        """Introspect ``information_schema`` for base tables in the ``public`` schema."""
        def introspect() -> list[dict]:
            import psycopg2
            conn = psycopg2.connect(self._uri.raw(), connect_timeout=5)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
                )
                names = [r[0] for r in cur.fetchall()]
                tables: list[dict] = []
                for name in names:
                    cur.execute(
                        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                        (name,),
                    )
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

        return self._with_timeout(introspect, "introspect")

    def discover_relationships(self) -> list[dict]:
        """Foreign keys from ``information_schema`` in the canonical FK-edge format (``[]`` on failure)."""
        def introspect() -> list[dict]:
            import psycopg2
            conn = psycopg2.connect(self._uri.raw(), connect_timeout=5)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "  ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema "
                    "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"
                )
                return [{"from_table": r[0], "from_column": r[1], "to_table": r[2], "to_column": r[3]}
                        for r in cur.fetchall()]
            finally:
                conn.close()

        try:
            return self._with_timeout(introspect, "introspect")
        except DatasetConnectionError:
            return []

    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS):
        """ATTACH the database read-only in DuckDB and expose one view per **given** table (no introspect)."""
        import duckdb

        conn = new_connection()
        try:
            conn.execute("INSTALL postgres")
            conn.execute("LOAD postgres")
            dsn = self._libpq_dsn().replace("'", "''")
            conn.execute(f"ATTACH '{dsn}' AS pgdb (TYPE postgres, READ_ONLY)")
            for name in table_names:
                safe = name.replace('"', '""')
                conn.execute(f'CREATE VIEW "{safe}" AS SELECT * FROM pgdb.public."{safe}"')
        except duckdb.Error as exc:
            conn.close()
            raise DatasetConnectionError(f"Could not attach {self._uri.display()}: {self._sanitize(exc)}")
        return build_server(self._server.get("name") or "database", conn,
                            [{"table_name": n} for n in table_names], max_rows)

    # ---- helpers ---------------------------------------------------------

    def _with_timeout(self, fn, verb: str):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(fn).result(timeout=_CONNECT_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError:
            raise DatasetConnectionError(f"Timed out trying to {verb} {self._uri.display()}.")
        except Exception as exc:
            raise DatasetConnectionError(f"Could not {verb} {self._uri.display()}: {self._sanitize(exc)}")

    def _libpq_dsn(self) -> str:
        """Build a libpq conninfo string from the URI (raw password used only here)."""
        p = urlsplit(self._uri.raw())
        parts = []
        if p.hostname:
            parts.append(f"host={p.hostname}")
        if p.port:
            parts.append(f"port={p.port}")
        if p.path.lstrip("/"):
            parts.append(f"dbname={p.path.lstrip('/')}")
        if p.username:
            parts.append(f"user={p.username}")
        if p.password:
            parts.append(f"password={p.password}")
        return " ".join(parts)

    def _sanitize(self, exc: Exception) -> str:
        """Scrub the raw URI + password out of a driver error message."""
        msg = str(exc).replace(self._uri.raw(), self._uri.display())
        password = urlsplit(self._uri.raw()).password
        if password:
            msg = msg.replace(password, "***")
        return msg
