"""Golden-path UI smoke test: upload CSV → create MCP server (auto-sync) → create session → ask a
question → see the answer inline. Stub mode, tmp SQLite."""
import csv
import io
import re

import pytest
from fastapi.testclient import TestClient

import data_analysis_agent.db.session as session_module
from data_analysis_agent.db.database import Database


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("DATAANALYSIS_DATABASE_URL", "sqlite:///golden_test.db")
    monkeypatch.setenv("DATAANALYSIS_OPENROUTER_API_KEY", "")


@pytest.fixture(autouse=True)
def _use_sqlite(tmp_path, monkeypatch):
    db = Database(f"sqlite:///{tmp_path / 'golden.db'}")
    db._init_schema()
    monkeypatch.setattr(session_module, "_db", db)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    monkeypatch.setenv("DATAANALYSIS_CHECKPOINT_DB", str(tmp_path / "ckpt.db"))
    monkeypatch.setenv("DATAANALYSIS_DATASETS_DIR", str(tmp_path / "datasets"))
    yield
    db._dispose()
    monkeypatch.setattr(session_module, "_db", None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAANALYSIS_UPLOAD_DIR", str(tmp_path / "uploads"))
    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None
    from data_analysis_agent.api import create_app
    with TestClient(create_app(), raise_server_exceptions=True) as c:
        yield c


def _make_csv() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["product", "revenue", "units"])
    writer.writerow(["Widget A", 5000, 25])
    writer.writerow(["Widget B", 3000, 15])
    return buf.getvalue().encode()


def _create_server(client, name: str, filename: str = "data.csv") -> str:
    """Run the upload → create two-step the UI performs; return the home HTML after create."""
    up = client.post("/database/upload", data={"database_name": name},
                     files={"file": (filename, _make_csv(), "text/csv")})
    assert up.status_code == 200, up.text
    uri = up.json()["uri"]
    r = client.post("/database", data={"name": name, "database_type": "parquet", "database_uri": uri},
                    follow_redirects=True)
    assert r.status_code == 200, r.text
    return r.text


def test_home_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Databases" in r.text
    assert "Sessions" in r.text


def test_stub_banner_visible_on_home(client):
    assert "Stub mode" in client.get("/").text


def test_create_server_shows_on_home(client):
    html = _create_server(client, "Sales DB")
    assert "Sales DB" in html


def test_golden_path_end_to_end(client):
    # 1. Upload CSV + create the MCP server (which auto-syncs into tools/resources/prompts)
    home = _create_server(client, "Test DB", "test_data.csv")

    # 2. Extract the server id from the session-create checkboxes, then create a session
    m = re.search(r'name="database_ids" value="([^"]+)"', home)
    assert m, "database_ids checkbox not found on home page"
    database_id = m.group(1)
    r2 = client.post("/sessions", data={"database_ids": database_id}, follow_redirects=True)
    assert r2.status_code == 200
    session_id = str(r2.url).rstrip("/").split("/")[-1].split("?")[0]

    # 3. Ask a question
    r3 = client.post(f"/sessions/{session_id}/query",
                     data={"question": "What is the total revenue?"}, follow_redirects=True)
    assert r3.status_code == 200
    assert "stub" in r3.text.lower() or "analysis" in r3.text.lower()
    assert "total revenue" in r3.text.lower()


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
