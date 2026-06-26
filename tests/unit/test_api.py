"""API contract tests for the Phase-2 surface — offline, no LLM key required.

The old boilerplate `POST /runs` contract (single-arg `run_agent(input_text)`)
has been retired; the canonical analysis route is now `POST /ask`. These tests
cover the always-on, graph-free surface: `/health`, `/runs/current`, and the
`/ask` validation guards. They run against the stub provider + in-memory SQLite
via the `api_client` fixture (no network).
"""
import pytest


@pytest.fixture(autouse=True)
def _force_stub_provider(monkeypatch):
    """Pin the offline stub provider regardless of any key present in `.env`.

    The unit suite is the offline guarantee — it must not touch the network even
    when a real key happens to be configured locally. Setting the env var ahead
    of the autouse settings-singleton reset makes both `/health` and the graph
    resolve to `stub`.
    """
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "stub")
    import config.settings as m
    m._settings = None


def test_health_returns_provider(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "ok"
    # provider drives the UI stub banner; with no key set, auto-detect -> stub
    assert data["provider"] == "stub"


def test_runs_current_idle_when_empty(api_client):
    r = api_client.get("/runs/current")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["run_id"] is None
    assert data["status"] == "idle"
    assert "max_iterations" in data


def test_get_run_not_found(api_client):
    r = api_client.get("/runs/nonexistent-id")
    assert r.status_code == 404


def test_ask_rejects_empty_question(api_client):
    r = api_client.post("/ask", json={"question": "", "dataset_id": "anything"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "empty_question"


def test_ask_rejects_when_no_datasets_uploaded(api_client):
    r = api_client.post("/ask", json={"question": "What is the average?"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "no_datasets"
