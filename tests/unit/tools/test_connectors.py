"""Unit tests for the connector seam: DatasetURI (credential-free display) and the ParquetConnector
(connection-check + build a server with a generic ``query`` tool and within-server JOINs), exercised
through the real in-memory MCP client."""
import asyncio

import pandas as pd
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from data_analysis_agent.tools.connectors.base import DatasetConnectionError, get_connector
from data_analysis_agent.tools.connectors.parquet import ParquetConnector
from data_analysis_agent.tools.connectors.uri import DatasetURI


def test_uri_internal_parquet():
    u = DatasetURI("parquet:///Q2%20Sales")
    assert u.scheme == "parquet"
    assert u.is_internal is True
    assert u.database == "Q2 Sales"       # URL-decoded
    assert u.host is None and u.username is None and u.has_password is False
    assert u.display() == "parquet:///Q2%20Sales"


def test_uri_external_strips_credentials():
    u = DatasetURI("postgresql://analyst:secret@db.internal:5432/sales")
    assert u.scheme == "postgresql"
    assert u.host == "db.internal" and u.port == 5432
    assert u.username == "analyst" and u.has_password is True
    assert u.database == "sales"
    shown = u.display()
    assert shown == "postgresql://db.internal:5432/sales"
    assert "secret" not in shown and "analyst" not in shown  # credentials never displayed


def _two_table_server(tmp_path, monkeypatch):
    """A parquet database whose two tables the connector will discover from its datasets directory."""
    monkeypatch.setenv("DATAANALYSIS_DATASETS_DIR", str(tmp_path / "datasets"))
    directory = tmp_path / "datasets" / "sales_db"
    directory.mkdir(parents=True)
    pd.DataFrame({"id": [1, 2, 3], "cust": [10, 10, 20], "amount": [5, 7, 3]}).to_parquet(directory / "orders.parquet")
    pd.DataFrame({"id": [10, 20], "region": ["N", "S"]}).to_parquet(directory / "customers.parquet")
    return {"name": "sales_db", "type": "parquet", "uri": "parquet:///sales_db"}


def test_parquet_connection_check_ok_and_corrupt(tmp_path, monkeypatch):
    server = _two_table_server(tmp_path, monkeypatch)
    ParquetConnector(server).connection_check()  # no raise

    (tmp_path / "datasets" / "sales_db" / "broken.parquet").write_text("not a parquet file")
    with pytest.raises(DatasetConnectionError):
        ParquetConnector(server).connection_check()


def test_get_connector_dispatches_to_parquet(tmp_path, monkeypatch):
    server = _two_table_server(tmp_path, monkeypatch)
    assert isinstance(get_connector(server), ParquetConnector)


def test_get_connector_dispatches_by_type():
    from data_analysis_agent.tools.connectors.postgres import PostgresConnector
    from data_analysis_agent.tools.connectors.sqlite import SQLiteConnector
    from data_analysis_agent.tools.connectors.mongodb import MongoDBConnector
    from data_analysis_agent.tools.connectors.snowflake import SnowflakeConnector
    # External databases are always enabled; dispatch attempts no connection (drivers import lazily).
    assert isinstance(get_connector({"name": "x", "type": "postgresql", "uri": "postgresql://h/db"}), PostgresConnector)
    assert isinstance(get_connector({"name": "x", "type": "sqlite", "uri": "sqlite:///x.db"}), SQLiteConnector)
    assert isinstance(get_connector({"name": "x", "type": "mongodb", "uri": "mongodb://h/db"}), MongoDBConnector)
    assert isinstance(get_connector({"name": "x", "type": "snowflake", "uri": "snowflake://u:p@a/DB/SC"}), SnowflakeConnector)


def test_sqlite_connector_discovers_and_queries(tmp_path):
    import sqlite3
    from data_analysis_agent.tools.connectors.sqlite import SQLiteConnector
    db_path = tmp_path / "shop.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE orders (id INTEGER, amount INTEGER)")
    conn.executemany("INSERT INTO orders VALUES (?, ?)", [(1, 5), (2, 7)])
    conn.commit()
    conn.close()

    c = SQLiteConnector({"name": "shop", "type": "sqlite", "uri": f"sqlite:///{db_path}"})
    c.connection_check()  # no raise
    tables = c.discover_tables()
    assert [t["table_name"] for t in tables] == ["orders"]
    assert tables[0]["column_names"] == ["id", "amount"] and tables[0]["row_count"] == 2

    try:
        fast = c.build_server(["orders"])
    except DatasetConnectionError as exc:
        pytest.skip(f"duckdb sqlite extension unavailable offline: {exc}")

    async def body():
        async with create_connected_server_and_client_session(fast) as s:
            res = await s.call_tool("query", {"query": "SELECT SUM(amount) AS t FROM orders"})
            return res.content[0].text, res.isError

    text, is_error = asyncio.run(body())
    fast._duckdb_conn.close()
    assert is_error is False and text.strip() == "t\n12"


def test_sqlite_discovers_foreign_keys(tmp_path):
    import sqlite3
    from data_analysis_agent.tools.connectors.sqlite import SQLiteConnector
    db_path = tmp_path / "fk.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, "
                 "customer_id INTEGER REFERENCES customers(id))")
    conn.commit()
    conn.close()
    rels = SQLiteConnector({"name": "fk", "type": "sqlite", "uri": f"sqlite:///{db_path}"}).discover_relationships()
    assert rels == [{"from_table": "orders", "from_column": "customer_id",
                     "to_table": "customers", "to_column": "id"}]   # canonical FK-edge format


def test_parquet_build_server_generic_query_with_join(tmp_path, monkeypatch):
    server = _two_table_server(tmp_path, monkeypatch)
    fast = ParquetConnector(server).build_server(["orders", "customers"])

    async def body():
        async with create_connected_server_and_client_session(fast) as s:
            listed = await s.list_tools()
            names = sorted(t.name for t in listed.tools)
            res = await s.call_tool("query", {
                "query": "SELECT c.region, SUM(o.amount) AS total FROM orders o "
                         "JOIN customers c ON o.cust = c.id GROUP BY c.region ORDER BY c.region"
            })
            return names, res.content[0].text, res.isError

    names, text, is_error = asyncio.run(body())
    fast._duckdb_conn.close()
    assert names == ["query"]   # one generic tool per server
    assert is_error is False
    assert text.strip() == "region,total\nN,12\nS,3"
