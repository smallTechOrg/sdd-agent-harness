"""Unit tests for the DuckDB analytical engine + deterministic seed.

Each test runs against an isolated temp DuckDB file (never the real one) and
seeds the ``sales`` table itself, so there is no reliance on agent startup.
"""
import pytest

import config.settings as settings_module
from analytics import duckdb_engine
from analytics.seed import seed_sales, SALES_TABLE


@pytest.fixture
def temp_duckdb(tmp_path, monkeypatch):
    """Isolated DuckDB file with a fresh process-global connection."""
    db_file = tmp_path / "test_analytics.duckdb"
    # Force settings to point at the temp DB and reset the singleton.
    settings_module._settings = None
    monkeypatch.setenv("AGENT_DUCKDB_PATH", str(db_file))
    monkeypatch.setenv("AGENT_SAMPLE_ROW_COUNT", "3")
    monkeypatch.setenv("AGENT_RESULT_ROW_CAP", "10")
    duckdb_engine.reset_connection()
    yield duckdb_engine.get_connection()
    duckdb_engine.reset_connection()
    settings_module._settings = None


def test_seed_is_idempotent(temp_duckdb):
    first = seed_sales(temp_duckdb)
    assert first["created"] is True
    assert first["row_count"] == 200

    second = seed_sales(temp_duckdb)
    assert second["created"] is False
    assert second["row_count"] == 200

    total = temp_duckdb.execute(f"SELECT COUNT(*) FROM {SALES_TABLE}").fetchone()[0]
    assert total == 200


def test_introspect_returns_schema_and_bounded_sample(temp_duckdb):
    seed_sales(temp_duckdb)
    info = duckdb_engine.introspect(SALES_TABLE)

    cols = {c["column"] for c in info["schema"]}
    assert cols == {"order_id", "order_date", "region", "product", "quantity", "amount"}

    # Types are present (DuckDB reports e.g. INTEGER, DATE, VARCHAR, DOUBLE).
    by_name = {c["column"]: c["type"].upper() for c in info["schema"]}
    assert "INT" in by_name["order_id"]
    assert by_name["order_date"] == "DATE"
    assert "VARCHAR" in by_name["region"] or "STRING" in by_name["region"]
    assert "DOUBLE" in by_name["amount"] or "FLOAT" in by_name["amount"]

    # Sample is bounded by sample_row_count (3), never the full 200-row table.
    assert len(info["sample_rows"]) == 3


def test_introspect_unknown_table_raises(temp_duckdb):
    seed_sales(temp_duckdb)
    with pytest.raises(ValueError):
        duckdb_engine.introspect("does_not_exist")


def test_run_select_returns_columns_and_rows(temp_duckdb):
    seed_sales(temp_duckdb)
    result = duckdb_engine.run_select(
        "SELECT region, SUM(amount) AS total FROM sales GROUP BY region ORDER BY region"
    )
    assert result["columns"] == ["region", "total"]
    regions = {row[0] for row in result["rows"]}
    assert regions == {"North", "South", "East", "West"}
    # Each total is a positive number.
    assert all(row[1] > 0 for row in result["rows"])


def test_run_select_respects_row_cap(temp_duckdb):
    seed_sales(temp_duckdb)
    # result_row_cap is 10 in this fixture; the table has 200 rows.
    result = duckdb_engine.run_select("SELECT * FROM sales")
    assert len(result["rows"]) == 10


def test_run_select_rejects_non_select_before_execution(temp_duckdb):
    seed_sales(temp_duckdb)
    with pytest.raises(ValueError):
        duckdb_engine.run_select("DROP TABLE sales")
    # The table must still be intact (the statement never reached the engine).
    total = temp_duckdb.execute(f"SELECT COUNT(*) FROM {SALES_TABLE}").fetchone()[0]
    assert total == 200
