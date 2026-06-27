"""Integration-test fixtures: an isolated, seeded DuckDB.

These tests run the FULL path against REAL Gemini. The DuckDB analytical engine
is pointed at a temp file and seeded with the `sales` table here, so the gate is
self-contained — no manual setup and no reliance on agent.py startup.
"""
import pytest

import config.settings as settings_module
from analytics import duckdb_engine


@pytest.fixture(autouse=True)
def seeded_duckdb(tmp_path, monkeypatch):
    """Point DuckDB at a temp file and seed the `sales` table before each test."""
    db_file = tmp_path / "analytics.duckdb"
    monkeypatch.setenv("AGENT_DUCKDB_PATH", str(db_file))
    # Reset the settings singleton so the new env var is picked up.
    settings_module._settings = None
    duckdb_engine.reset_connection()

    from analytics.seed import seed_sales
    seed_sales()

    yield

    duckdb_engine.reset_connection()
    settings_module._settings = None
