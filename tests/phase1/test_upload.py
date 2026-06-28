"""
Phase 1 integration tests — upload endpoint, profiler, file list, sessions stub.

Uses a real CSV file and a real in-process FastAPI TestClient with an isolated
SQLite database (tmpdir). No LLM key required for these tests.
"""
import io

import pytest
from fastapi.testclient import TestClient

# Build a 10-row CSV for testing
SAMPLE_CSV = """name,age,score,city
Alice,30,95.5,NYC
Bob,25,87.2,LA
Carol,35,91.0,Chicago
Dave,28,76.5,NYC
Eve,32,88.8,LA
Frank,29,93.2,Chicago
Grace,31,84.7,NYC
Henry,27,90.1,LA
Iris,33,78.3,Chicago
Jack,26,96.0,NYC
"""


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """TestClient with isolated SQLite DB and uploads dir."""
    import data_analysis.config.settings as settings_module
    import data_analysis.db.session as session_module
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from data_analysis.db.models import Base

    # Reset settings singleton so env overrides are picked up
    settings_module._settings = None

    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("AGENT_DATABASE_URL", db_url)
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "test-key")

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)

    # Redirect uploads to tmp_path so tests don't pollute the repo
    import data_analysis.api.upload as upload_module
    from pathlib import Path

    monkeypatch.setattr(upload_module, "UPLOAD_DIR", tmp_path / "uploads")

    from data_analysis.api import create_app

    test_app = create_app()

    with TestClient(test_app, raise_server_exceptions=True) as client:
        yield client

    settings_module._settings = None
    engine.dispose()


def test_health(app_client):
    r = app_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_csv_returns_profile(app_client):
    """Upload a CSV and verify the profile contains correct metadata."""
    csv_bytes = SAMPLE_CSV.encode()
    r = app_client.post(
        "/api/files/upload",
        files={"file": ("test_data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["original_filename"] == "test_data.csv"
    assert "file_id" in data
    assert "profile" in data
    profile = data["profile"]
    assert profile["row_count"] == 10
    assert profile["column_count"] == 4
    assert len(profile["columns"]) == 4
    col_names = [c["name"] for c in profile["columns"]]
    assert "name" in col_names
    assert "age" in col_names


def test_upload_profile_includes_sample_values(app_client):
    """Profile must include up to 3 sample values per column."""
    csv_bytes = SAMPLE_CSV.encode()
    r = app_client.post(
        "/api/files/upload",
        files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    profile = r.json()["profile"]
    name_col = next(c for c in profile["columns"] if c["name"] == "name")
    assert len(name_col["sample_values"]) == 3
    assert name_col["null_count"] == 0


def test_upload_invalid_extension(app_client):
    """Non-CSV/Excel files must return 400."""
    r = app_client.post(
        "/api/files/upload",
        files={"file": ("data.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400


def test_list_files_after_upload(app_client):
    """Uploaded file must appear in GET /api/files."""
    csv_bytes = SAMPLE_CSV.encode()
    upload_r = app_client.post(
        "/api/files/upload",
        files={"file": ("list_test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert upload_r.status_code == 200
    file_id = upload_r.json()["file_id"]

    list_r = app_client.get("/api/files")
    assert list_r.status_code == 200
    files = list_r.json()["files"]
    assert any(f["file_id"] == file_id for f in files)


def test_sessions_stub_returns_empty(app_client):
    """Phase 1: GET /api/sessions returns empty list."""
    r = app_client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json()["sessions"] == []


def test_upload_csv_with_nulls(app_client):
    """Profile correctly counts null values."""
    csv_with_nulls = "a,b,c\n1,,x\n2,2,\n3,3,z\n"
    r = app_client.post(
        "/api/files/upload",
        files={"file": ("nulls.csv", io.BytesIO(csv_with_nulls.encode()), "text/csv")},
    )
    assert r.status_code == 200
    profile = r.json()["profile"]
    b_col = next(c for c in profile["columns"] if c["name"] == "b")
    c_col = next(c for c in profile["columns"] if c["name"] == "c")
    assert b_col["null_count"] == 1
    assert c_col["null_count"] == 1
