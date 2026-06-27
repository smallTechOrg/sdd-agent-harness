"""MongoDB database connector (BETA): collections are the "tables".

MongoDB is not SQL, so there is no native DuckDB scanner. We introspect with ``pymongo`` (collections +
sampled field names) and, for querying, **load** each collection's documents into a DuckDB-registered
DataFrame so the generic read-only SELECT path works unchanged. ``pymongo`` is imported lazily — install
it (``pip install pymongo``) to use this type.
"""
from __future__ import annotations

from data_analysis_agent.tools.connectors.base import BaseConnector, DatasetConnectionError
from data_analysis_agent.tools.mcp.server import DEFAULT_MAX_ROWS, build_server, new_connection, register_dataframe_view

_SAMPLE_LIMIT = 2000  # documents loaded per collection for the query path (BETA)


class MongoDBConnector(BaseConnector):
    """Serves a `mongodb` database; introspects + loads collections via pymongo."""

    def _client(self):
        try:
            import pymongo
        except ImportError:
            raise DatasetConnectionError("MongoDB support requires 'pymongo' (pip install pymongo).")
        return pymongo.MongoClient(self._uri.raw(), serverSelectionTimeoutMS=5000)

    def _db(self, client):
        from pymongo.uri_parser import parse_uri
        name = parse_uri(self._uri.raw()).get("database")
        if not name:
            raise DatasetConnectionError("MongoDB URI must include a database name (mongodb://host/db).")
        return client[name]

    def connection_check(self) -> None:
        """Connect + ``ping``; raise a sanitized error on failure."""
        try:
            client = self._client()
            try:
                client.admin.command("ping")
            finally:
                client.close()
        except DatasetConnectionError:
            raise
        except Exception as exc:
            raise DatasetConnectionError(f"Could not connect to {self._uri.display()}: {exc}")

    def discover_tables(self) -> list[dict]:
        """List collections and infer columns from a sampled document."""
        try:
            client = self._client()
            try:
                db = self._db(client)
                tables: list[dict] = []
                for coll in db.list_collection_names():
                    doc = db[coll].find_one() or {}
                    cols = [k for k in doc.keys() if k != "_id"]
                    tables.append({
                        "table_name": coll,
                        "column_names": cols,
                        "schema": [{"name": k, "dtype": type(doc[k]).__name__, "nullable": True} for k in cols],
                        "row_count": db[coll].estimated_document_count(),
                    })
                return tables
            finally:
                client.close()
        except DatasetConnectionError:
            raise
        except Exception as exc:
            raise DatasetConnectionError(f"Could not introspect {self._uri.display()}: {exc}")

    def build_server(self, table_names: list[str], max_rows: int = DEFAULT_MAX_ROWS):
        """Load each **given** collection (capped) into a DuckDB-registered DataFrame (no introspect)."""
        import pandas as pd
        client = self._client()
        conn = new_connection()
        try:
            db = self._db(client)
            for name in table_names:
                docs = list(db[name].find(limit=_SAMPLE_LIMIT))
                for d in docs:
                    d.pop("_id", None)
                df = pd.json_normalize(docs) if docs else pd.DataFrame()
                register_dataframe_view(conn, name, df)
            return build_server(self._server.get("name") or "database", conn,
                                [{"table_name": n} for n in table_names], max_rows)
        finally:
            client.close()
