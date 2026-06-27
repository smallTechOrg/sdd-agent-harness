"""
Phase 1 backend tests.

- Synthetic 200-row CSV fixture with 12 columns (date, category, 10 numerics, outlier in row 50)
- Isolated SQLite DB (monkeypatched engine + SessionLocal)
- Real Gemini API used when key present; tests skip when absent
"""
from __future__ import annotations

import io
import json
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_csv_bytes() -> bytes:
    """
    200-row CSV with 12 columns:
    - date (YYYY-MM-DD, daily from 2024-01-01)
    - category (3 values: A, B, C)
    - val_1 through val_10 (numeric, normally distributed)
    - Row 50: val_1 is set to 100x the mean (injected outlier)
    """
    rng = np.random.default_rng(42)
    n = 200

    dates = pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    categories = ["A", "B", "C"]
    cat_col = [categories[i % 3] for i in range(n)]

    data = {
        "date": dates,
        "category": cat_col,
    }
    for i in range(1, 11):
        col = rng.normal(loc=100.0, scale=10.0, size=n)
        data[f"val_{i}"] = col

    df = pd.DataFrame(data)

    # Inject outlier: row 50, val_1 = 100 * mean
    mean_val1 = float(df["val_1"].mean())
    df.loc[50, "val_1"] = mean_val1 * 100

    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


@pytest.fixture
def isolated_engine(tmp_path, monkeypatch):
    """Isolated SQLite DB; patches db.session globals so all sessions use this engine."""
    from db.models import Base
    import db.session as session_module

    engine = create_engine(f"sqlite:///{tmp_path}/test_phase1.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)

    yield engine
    engine.dispose()


@pytest.fixture
def api_client(isolated_engine):
    """TestClient wired to isolated DB."""
    from api import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def require_gemini_key():
    """Skip if no Gemini key is set."""
    from config.settings import get_settings
    s = get_settings()
    if not s.gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")


# ---------------------------------------------------------------------------
# Unit: graph compiles
# ---------------------------------------------------------------------------

def test_graph_compiles():
    """Graph compiles without any env vars."""
    from graph.agent import agentic_ai
    assert agentic_ai is not None


# ---------------------------------------------------------------------------
# Unit: file ingest
# ---------------------------------------------------------------------------

def test_file_ingest(isolated_engine, synthetic_csv_bytes):
    """ingest_file parses CSV, writes SQLite table, returns correct metadata."""
    from ingest.file_ingest import ingest_file

    result = ingest_file(
        file_bytes=synthetic_csv_bytes,
        filename="test_data.csv",
        session_id="test-session-001",
        engine=isolated_engine,
    )

    assert result["table_name"] == "t_test_data"
    assert result["row_count"] == 200
    assert "date" in result["columns"]
    assert "category" in result["columns"]
    assert "val_1" in result["columns"]
    assert len(result["columns"]) == 12

    # Verify table actually exists in SQLite
    inspector = inspect(isolated_engine)
    table_names = inspector.get_table_names()
    assert "t_test_data" in table_names

    # Verify row count
    from sqlalchemy import text
    with isolated_engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM t_test_data")).scalar()
    assert count == 200


# ---------------------------------------------------------------------------
# Integration: full pipeline (requires real Gemini)
# ---------------------------------------------------------------------------

def test_full_analysis_pipeline(api_client, isolated_engine, synthetic_csv_bytes, require_gemini_key):
    """
    Full E2E: create session -> upload CSV -> analyze -> assert results.
    Uses real Gemini API.
    """
    # 1. Create session
    r = api_client.post("/sessions")
    assert r.status_code == 200, r.text
    session_id = r.json()["data"]["session_id"]
    assert session_id

    # 2. Upload CSV
    r = api_client.post(
        f"/sessions/{session_id}/files",
        files={"file": ("test_data.csv", synthetic_csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    upload_data = r.json()["data"]
    assert upload_data["table_name"] == "t_test_data"
    assert upload_data["row_count"] == 200

    # 3. Analyze — question asks to show all values so we get raw rows (needed for anomaly detection)
    r = api_client.post(
        f"/sessions/{session_id}/analyze",
        json={"question": "Show me all val_1 values and their categories. Are there any outliers?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    # Status
    assert data["status"] == "completed", f"status={data['status']}, error={data.get('error')}"

    # SQL
    assert data["sql_query"], "sql_query should be non-empty"
    assert "SELECT" in data["sql_query"].upper(), "sql_query should contain SELECT"

    # insight_json structure
    ij = data["insight_json"]
    assert ij is not None, "insight_json should not be None"
    assert "numeric_columns" in ij, "insight_json should have numeric_columns"
    assert ij["numeric_columns"], "numeric_columns should be non-empty"

    # Each numeric column entry should have min, max, mean
    for col_name, col_stats in ij["numeric_columns"].items():
        assert "min" in col_stats, f"col {col_name} missing min"
        assert "max" in col_stats, f"col {col_name} missing max"
        assert "mean" in col_stats, f"col {col_name} missing mean"

    # Anomalies: injected outlier in row 50 (val_1 = 100x mean) must be detected
    assert "anomalies" in ij, "insight_json should have anomalies key"
    assert len(ij["anomalies"]) >= 1, (
        f"Expected at least 1 anomaly (injected outlier in val_1), got: {ij['anomalies']}"
    )

    # chart_specs
    assert data["chart_specs"] is not None, "chart_specs should not be None"
    assert len(data["chart_specs"]) >= 1, "Should have at least 1 chart spec"
    valid_types = {"line", "bar", "histogram", "scatter"}
    for spec in data["chart_specs"]:
        assert spec.get("chart_type") in valid_types, f"Unknown chart type: {spec.get('chart_type')}"

    # output_text / insight_text
    text_val = data.get("output_text") or data.get("insight_text") or ""
    assert 50 <= len(text_val) <= 800, (
        f"insight_text length {len(text_val)} out of expected range 50-800"
    )


# ---------------------------------------------------------------------------
# Edge case: empty question → 422
# ---------------------------------------------------------------------------

def test_analyze_empty_question(api_client, isolated_engine, synthetic_csv_bytes):
    """Empty question string must return HTTP 422."""
    # Create session + upload file first
    r = api_client.post("/sessions")
    assert r.status_code == 200
    session_id = r.json()["data"]["session_id"]

    r = api_client.post(
        f"/sessions/{session_id}/files",
        files={"file": ("data.csv", synthetic_csv_bytes, "text/csv")},
    )
    assert r.status_code == 200

    # Send empty question
    r = api_client.post(
        f"/sessions/{session_id}/analyze",
        json={"question": ""},
    )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Edge case: file too large → 413
# ---------------------------------------------------------------------------

def test_file_too_large(api_client, isolated_engine):
    """A file larger than 50 MB must return HTTP 413."""
    # Create session
    r = api_client.post("/sessions")
    assert r.status_code == 200
    session_id = r.json()["data"]["session_id"]

    # Build a fake ~60 MB binary payload (not valid CSV, but size check happens first)
    large_content = b"x" * (60 * 1024 * 1024)

    r = api_client.post(
        f"/sessions/{session_id}/files",
        files={"file": ("big_file.csv", large_content, "text/csv")},
    )
    assert r.status_code == 413, f"Expected 413, got {r.status_code}: {r.text}"
