"""
Real Gemini integration test.

Requires GEMINI_API_KEY to be set.  All tests in this module are skipped
when the key is absent, so the offline CI gate (GEMINI_API_KEY="") stays green.
"""
import csv
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Mark all tests in this module as integration (skips without real key)
pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_gemini_key():
    """Skip all tests in this module if GEMINI_API_KEY is not set."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        pytest.skip("GEMINI_API_KEY not set — skipping integration tests")


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Reset lru_cache on get_settings() so env overrides take effect."""
    from analyst.config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def setup_env(tmp_path, monkeypatch):
    """Set up a temp DB and data dir so the integration test is self-contained."""
    db_path = tmp_path / "integration_test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setenv("ANALYST_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANALYST_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ANALYST_SECRET_KEY", "integration-test-secret")

    # Re-clear after monkeypatching so settings picks up new env vars
    from analyst.config.settings import get_settings

    get_settings.cache_clear()

    # Rebuild DB engine with new settings
    import analyst.db.session as db_session_module
    from sqlalchemy.orm import sessionmaker

    new_engine = db_session_module._make_engine()
    db_session_module.engine = new_engine
    db_session_module.SessionLocal = sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False
    )

    yield


@pytest.fixture
def csv_file(tmp_path: Path) -> str:
    """Write a small test CSV and return its absolute path."""
    p = tmp_path / "orders.csv"
    with open(p, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["order_id", "customer", "amount"])
        writer.writerow([1, "Acme Corp", 150.00])
        writer.writerow([2, "Beta Ltd", 200.00])
        writer.writerow([3, "Acme Corp", 75.00])
    return str(p)


def test_end_to_end_real_gemini(setup_env, csv_file):
    """
    Upload a CSV, submit a NL question, verify Gemini returns real (non-stub) SQL
    and DuckDB executes it successfully.
    """
    # Clear settings cache so the real key is picked up
    from analyst.config.settings import get_settings

    get_settings.cache_clear()

    from analyst.api import create_app

    app = create_app()

    with TestClient(app) as client:
        # 1. Create a session
        r = client.post("/api/sessions")
        assert r.status_code == 200
        session_id = r.json()["session_id"]

        # 2. Upload the CSV
        with open(csv_file, "rb") as f:
            r = client.post(
                "/api/datasets",
                files={"file": ("orders.csv", f, "text/csv")},
                cookies={"session_id": session_id},
            )
        assert r.status_code == 200, f"Dataset upload failed: {r.text}"
        meta = r.json()
        assert meta["name"] == "orders"
        assert len(meta["columns"]) == 3

        # 3. Submit a NL question
        r = client.post(
            "/api/query",
            json={"question": "How many orders does each customer have?"},
            cookies={"session_id": session_id},
        )
        assert r.status_code == 200, f"Query failed: {r.text}"
        result = r.json()

        # 4. Verify it's real Gemini SQL (not the stub)
        assert "stub-nl-query" not in result["sql"], (
            f"Expected real SQL from Gemini, got stub: {result['sql']}"
        )
        assert "SELECT" in result["sql"].upper()
        assert isinstance(result["rows"], list)
        assert len(result["rows"]) > 0  # Acme Corp=2, Beta Ltd=1

        # 5. Verify stub_mode is False
        r = client.get("/api/sessions/current", cookies={"session_id": session_id})
        assert r.status_code == 200
        assert r.json()["stub_mode"] is False
