"""Golden-path smoke: real Gemini end-to-end upload -> ask -> narrative + table.

Runs against the real Gemini API using AGENT_GEMINI_API_KEY from .env, real
DuckDB, and an isolated tmp SQLite metadata DB. Skips ONLY if no Gemini key is
configured (it is set in .env, so this must actually run).
"""
import io

import pytest


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    """Isolated SQLite metadata DB + tmp DuckDB file, wired into settings + session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.models import Base
    import db.session as session_module
    import config.settings as settings_module

    # Isolated DuckDB path via settings env.
    duckdb_path = str(tmp_path / "test.duckdb")
    monkeypatch.setenv("AGENT_DUCKDB_PATH", duckdb_path)
    monkeypatch.setenv("AGENT_MAX_SAMPLE_ROWS", "5")
    settings_module._settings = None  # force re-read

    engine = create_engine(f"sqlite:///{tmp_path}/meta.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield {"duckdb_path": duckdb_path, "engine": engine}
    engine.dispose()
    settings_module._settings = None


@pytest.fixture
def client(isolated_stores):
    from fastapi.testclient import TestClient
    from api import app

    with TestClient(app) as c:
        yield c


_CSV = (
    "region,amount\n"
    "West,1200\n"
    "East,980\n"
    "North,1500\n"
    "South,640\n"
    "West,300\n"
    "East,220\n"
)


def test_ask_flow_real_gemini(client, isolated_stores):
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")

    # 1. Upload a tiny CSV dataset via the real endpoint.
    resp = client.post(
        "/datasets",
        files={"file": ("sales.csv", io.BytesIO(_CSV.encode()), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    dataset = resp.json()["data"]
    assert dataset["row_count"] == 6
    assert any(c["name"] == "region" for c in dataset["schema"])
    dataset_id = dataset["id"]
    session_id = dataset["session_id"]

    # Token economy: stored sample preview never exceeds the cap (5).
    assert len(dataset["sample_rows"]) <= 5

    # 2. Ask a real question -> real Gemini SQL + narrative.
    resp = client.post(
        "/ask",
        json={"dataset_id": dataset_id, "question": "What were total sales by region?"},
    )
    assert resp.status_code == 200, resp.text
    ask = resp.json()["data"]

    assert ask["status"] == "completed"
    assert ask["narrative"] and len(ask["narrative"].strip()) > 0
    assert ask["sql"] and ask["sql"].strip().lower().startswith(("select", "with"))
    assert isinstance(ask["columns"], list) and len(ask["columns"]) > 0
    assert isinstance(ask["rows"], list) and len(ask["rows"]) > 0
    assert isinstance(ask["row_count"], int)
    run_id = ask["run_id"]

    # 3. The ask wrote a completed audit row.
    resp = client.get("/audit", params={"session_id": session_id})
    assert resp.status_code == 200, resp.text
    entries = resp.json()["data"]
    assert len(entries) >= 1
    entry = next((e for e in entries if e["id"] == run_id), None)
    assert entry is not None
    assert entry["status"] == "completed"
    assert entry["nl_question"] == "What were total sales by region?"
    assert entry["generated_sql"]
    assert entry["row_count"] is not None
    assert entry["duration_ms"] is not None


def test_audit_export_csv(client, isolated_stores):
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")

    resp = client.post(
        "/datasets",
        files={"file": ("sales.csv", io.BytesIO(_CSV.encode()), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    dataset = resp.json()["data"]
    client.post(
        "/ask",
        json={"dataset_id": dataset["id"], "question": "How many rows are there?"},
    )

    resp = client.get("/audit/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "nl_question" in resp.text


def test_ask_unknown_dataset_returns_400(client, isolated_stores):
    resp = client.post(
        "/ask",
        json={"dataset_id": "does-not-exist", "question": "anything?"},
    )
    assert resp.status_code == 400, resp.text
