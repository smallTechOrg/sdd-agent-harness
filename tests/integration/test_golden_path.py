"""Golden-path UI smoke test: connect CSV, create session with it, ask question, see answer inline."""
import csv
import io

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

    yield

    db._dispose()
    monkeypatch.setattr(session_module, "_db", None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAANALYSIS_UPLOAD_DIR", str(tmp_path / "uploads"))
    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None

    from data_analysis_agent.api import create_app
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _make_csv() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["product", "revenue", "units"])
    writer.writerow(["Widget A", 5000, 25])
    writer.writerow(["Widget B", 3000, 15])
    return buf.getvalue().encode()


def test_home_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Data Sources" in r.text
    assert "Sessions" in r.text


def test_stub_banner_visible_on_home(client):
    r = client.get("/")
    assert "Stub mode" in r.text


def test_upload_csv_returns_to_home(client):
    csv_bytes = _make_csv()
    r = client.post(
        "/datasources/upload",
        files={"file": ("sales.csv", csv_bytes, "text/csv")},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "sales.csv" in r.text


def test_golden_path_end_to_end(client):
    # 1. Upload CSV
    csv_bytes = _make_csv()
    r1 = client.post(
        "/datasources/upload",
        files={"file": ("test_data.csv", csv_bytes, "text/csv")},
        follow_redirects=True,
    )
    assert r1.status_code == 200

    # Extract datasource_id from the home page response (it's in the checkbox values)
    import re
    ds_id_match = re.search(r'name="data_source_ids" value="([^"]+)"', r1.text)
    assert ds_id_match, "data_source_ids checkbox not found in home page"
    datasource_id = ds_id_match.group(1)

    # 2. Create session with that data source
    r2 = client.post(
        "/sessions",
        data={"data_source_ids": datasource_id},
        follow_redirects=True,
    )
    assert r2.status_code == 200
    session_url = str(r2.url)
    session_id = session_url.rstrip("/").split("/")[-1].split("?")[0]

    # 3. Ask a question
    r3 = client.post(
        f"/sessions/{session_id}/query",
        data={"question": "What is the total revenue?"},
        follow_redirects=True,
    )
    assert r3.status_code == 200
    assert "stub" in r3.text.lower() or "analysis" in r3.text.lower()
    assert "total revenue" in r3.text.lower()


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
