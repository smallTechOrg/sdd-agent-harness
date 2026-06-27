"""Phase-1 golden path — the full primary journey over real HTTP + real Gemini.

Walks the exact journey the user will test:
  1. POST /datasets uploading sales.csv as multipart `file`
  2. POST /ask with a plain-English question

Asserts RESPONSE CONTENT (not just status codes) against the spec/api.md
contract. Runs against an isolated tmp SQLite DB, tmp upload_dir, and tmp DuckDB
store so `data/` is never touched. The real-LLM steps skip only if
AGENT_GEMINI_API_KEY is genuinely absent.
"""

from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sales.csv"


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", str(tmp_path / "working.duckdb"))
    import config.settings as settings_module
    settings_module._settings = None
    import tools.duckdb_store as ds
    ds._conn = None
    ds._conn_path = None
    yield
    ds._conn = None
    ds._conn_path = None


def _upload(api_client):
    with open(FIXTURE, "rb") as fh:
        files = {"file": ("sales.csv", fh.read(), "text/csv")}
    return api_client.post("/datasets", files=files)


def test_upload_returns_profiled_dataset(api_client):
    r = _upload(api_client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dataset_id"]
    assert data["name"] == "sales.csv"
    assert data["row_count"] == 32
    col_names = {c["name"] for c in data["columns"]}
    assert "region" in col_names
    assert "revenue" in col_names
    # revenue is numeric in the fixture
    by_name = {c["name"]: c["type"] for c in data["columns"]}
    assert by_name["revenue"] == "number"
    assert by_name["region"] == "text"


def test_ask_rejects_empty_question(api_client):
    r = _upload(api_client)
    dataset_id = r.json()["data"]["dataset_id"]
    r2 = api_client.post("/ask", json={"dataset_id": dataset_id, "question": ""})
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "BAD_REQUEST"


@pytest.mark.usefixtures("_require_llm_key")
def test_full_journey_upload_then_ask(api_client):
    # 1) Upload
    up = _upload(api_client)
    assert up.status_code == 200, up.text
    dataset_id = up.json()["data"]["dataset_id"]
    assert up.json()["data"]["row_count"] == 32

    # 2) Ask, for real, against Gemini
    ask = api_client.post(
        "/ask",
        json={"dataset_id": dataset_id, "question": "total revenue by region"},
    )
    assert ask.status_code == 200, ask.text
    data = ask.json()["data"]

    assert data["status"] == "completed"
    assert data["question_id"]
    assert data["answer_text"] and len(data["answer_text"]) > 5

    chart = data["chart_spec"]
    assert isinstance(chart, dict)
    assert chart.get("type") == "bar"
    assert chart.get("x")
    series = chart.get("series")
    assert series, "chart_spec must include a non-empty series"

    # West is the top region in the fixture (8300 vs East 3500) — it must appear.
    flat = str(series)
    assert "West" in flat, f"expected 'West' in series, got: {series}"
