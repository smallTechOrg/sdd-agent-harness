"""Unit tests for the PostgresConnector (BETA): connection-check + introspection against a MOCKED
psycopg2, credential sanitization, and get_connector flag gating. One live test is skipped unless
DATAANALYSIS_TEST_PG_URI is set (the live Postgres path is BETA and not part of the offline gate)."""
import os

import pytest

from data_analysis_agent.tools.connectors.base import DatasetConnectionError, get_connector
from data_analysis_agent.tools.connectors.postgres import PostgresConnector

PG_DATASET = {"name": "pg", "type": "postgresql", "uri": "postgresql://u:secret@h:5432/db"}

_TABLES = {
    "orders": [("id", "integer", "NO"), ("amount", "integer", "YES")],
    "customers": [("id", "integer", "NO"), ("region", "text", "YES")],
}


class _FakeCursor:
    def __init__(self):
        self._rows: list = []

    def execute(self, sql, params=None):
        if "SELECT 1" in sql:
            self._rows = [(1,)]
        elif "information_schema.tables" in sql:
            self._rows = [(t,) for t in _TABLES]
        elif "information_schema.columns" in sql:
            self._rows = [(c[0], c[1], c[2]) for c in _TABLES[params[0]]]
        else:
            self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeConn:
    def cursor(self):
        return _FakeCursor()

    def close(self):
        pass


@pytest.fixture
def fake_pg(monkeypatch):
    monkeypatch.setattr("psycopg2.connect", lambda *a, **k: _FakeConn())


def test_connection_check_ok(fake_pg):
    PostgresConnector(PG_DATASET).connection_check()  # no raise


def test_discover_tables(fake_pg):
    tables = PostgresConnector(PG_DATASET).discover_tables()
    assert sorted(t["table_name"] for t in tables) == ["customers", "orders"]
    orders = next(t for t in tables if t["table_name"] == "orders")
    assert orders["column_names"] == ["id", "amount"]
    assert orders["schema"][0] == {"name": "id", "dtype": "integer", "nullable": False}


def test_connection_failure_sanitizes_credentials(monkeypatch):
    def boom(*a, **k):
        raise Exception("FATAL: auth failed; conninfo postgresql://u:secret@h:5432/db password=secret")
    monkeypatch.setattr("psycopg2.connect", boom)
    with pytest.raises(DatasetConnectionError) as ei:
        PostgresConnector(PG_DATASET).connection_check()
    msg = str(ei.value)
    assert "secret" not in msg                   # password scrubbed
    assert "postgresql://h:5432/db" in msg        # credential-free display present


def test_get_connector_dispatches_to_postgres():
    # External databases are always enabled; dispatch attempts no connection.
    assert isinstance(get_connector(PG_DATASET), PostgresConnector)


@pytest.mark.external_db
def test_live_postgres_roundtrip():
    uri = os.environ.get("DATAANALYSIS_TEST_PG_URI")
    if not uri:
        pytest.skip("set DATAANALYSIS_TEST_PG_URI to run the live Postgres test (BETA)")
    connector = PostgresConnector({"name": "live", "type": "postgresql", "uri": uri})
    connector.connection_check()
    assert isinstance(connector.discover_tables(), list)
