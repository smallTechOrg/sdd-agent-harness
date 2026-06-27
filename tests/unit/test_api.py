"""API contract tests for DataChat — fast, no LLM.

These exercise GET /health and the 400 validation paths of POST /datasets and
POST /ask. None of these paths reach Gemini, so no key is required. Each test
runs against an isolated tmp SQLite DB (the autouse `_isolated_db` fixture) plus
an isolated tmp upload_dir and DuckDB path so `data/` is never touched.
"""

import io

import pytest


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Isolate the upload dir and the DuckDB working store onto tmp_path."""
    monkeypatch.setenv("AGENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", str(tmp_path / "working.duckdb"))
    # Force the settings singleton to re-read the patched env.
    import config.settings as settings_module
    settings_module._settings = None
    # Reset the DuckDB connection so it reopens at the patched path.
    import tools.duckdb_store as ds
    ds._conn = None
    ds._conn_path = None
    yield


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"data": {"status": "ok"}, "error": None}


def test_datasets_rejects_non_csv(api_client):
    files = {"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = api_client.post("/datasets", files=files)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_UPLOAD"


def test_datasets_requires_file(api_client):
    r = api_client.post("/datasets")
    # Missing required multipart `file` field — FastAPI validation error.
    assert r.status_code == 422


def test_ask_rejects_empty_question(api_client):
    r = api_client.post("/ask", json={"dataset_id": "anything", "question": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_ask_rejects_unknown_dataset(api_client):
    r = api_client.post("/ask", json={"dataset_id": "does-not-exist", "question": "hi?"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_ask_missing_body_is_422(api_client):
    r = api_client.post("/ask", json={})
    assert r.status_code == 422
