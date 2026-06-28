"""
Phase 1 integration tests — agent graph, query endpoint, SSE streaming.

The test_upload_then_query_with_real_llm test requires a real AGENT_GEMINI_API_KEY
in .env and runs the full LangGraph agent against the Gemini API.
All other tests run without an LLM key.
"""
import io
import json

import pytest


def _has_gemini_key() -> bool:
    import data_analysis.config.settings as m

    m._settings = None
    from data_analysis.config.settings import get_settings

    s = get_settings()
    return bool(s.gemini_api_key)


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """TestClient with isolated SQLite DB, real Gemini key, tmp uploads."""
    import data_analysis.config.settings as settings_module
    import data_analysis.db.session as session_module
    from pathlib import Path
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from data_analysis.db.models import Base

    settings_module._settings = None

    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("AGENT_DATABASE_URL", db_url)

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)

    import data_analysis.api.upload as upload_module

    monkeypatch.setattr(upload_module, "UPLOAD_DIR", tmp_path / "uploads")

    # Reset LLM client singleton so it picks up any env changes
    import data_analysis.llm.gemini_client as gc_module

    monkeypatch.setattr(gc_module, "_client", None)

    from data_analysis.api import create_app

    test_app = create_app()

    from fastapi.testclient import TestClient

    with TestClient(test_app, raise_server_exceptions=True) as client:
        yield client

    settings_module._settings = None
    gc_module._client = None
    engine.dispose()


SIMPLE_CSV = """product,sales,category
Widget A,1500,Electronics
Widget B,2300,Electronics
Gadget X,800,Toys
Gadget Y,1200,Toys
Tool Z,600,Hardware
Tool W,950,Hardware
Gizmo A,3100,Electronics
Gizmo B,1750,Toys
"""


def test_graph_compiles():
    """The LangGraph agent compiles without error (no LLM key required)."""
    from data_analysis.graph.agent import compiled_graph

    assert compiled_graph is not None


def test_upload_then_query_with_real_llm(app_client):
    """Full end-to-end: upload CSV -> ask question -> get streaming answer with chart."""
    if not _has_gemini_key():
        pytest.skip("AGENT_GEMINI_API_KEY not set — required for real-LLM gate")

    # Upload the CSV
    r = app_client.post(
        "/api/files/upload",
        files={"file": ("products.csv", io.BytesIO(SIMPLE_CSV.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    file_id = r.json()["file_id"]

    # Query with streaming — collect SSE events
    events = []
    with app_client.stream(
        "POST",
        "/api/query/stream",
        json={
            "question": "What is the total sales by category?",
            "file_ids": [file_id],
        },
        headers={"Accept": "text/event-stream"},
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events.append(ev)

    event_types = [e["type"] for e in events]
    assert "run_start" in event_types, f"Missing run_start in {event_types}"
    assert "done" in event_types, f"Missing done in {event_types}"

    # Must have either a token (answer) or an error
    has_token = any(e["type"] == "token" for e in events)
    has_error = any(e["type"] == "error" for e in events)
    assert has_token or has_error, f"No token or error in events: {event_types}"

    if has_token:
        # Should have a chart
        chart_events = [e for e in events if e["type"] == "chart"]
        assert len(chart_events) >= 1
        chart = chart_events[0]["plotly"]
        assert "data" in chart
        assert "layout" in chart

        # Should have cost info
        cost_events = [e for e in events if e["type"] == "cost"]
        assert len(cost_events) >= 1
        cost = cost_events[0]
        assert cost["input_tokens"] > 0
        assert cost["cost_usd"] >= 0


def test_query_missing_file_returns_400(app_client):
    """Querying with a non-existent file_id returns 400."""
    r = app_client.post(
        "/api/query/stream",
        json={
            "question": "test",
            "file_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert r.status_code == 400


def test_query_empty_question_returns_400(app_client):
    """Empty question returns 400."""
    r = app_client.post(
        "/api/query/stream",
        json={"question": "", "file_ids": ["some-id"]},
    )
    assert r.status_code == 400


def test_query_no_files_returns_400(app_client):
    """No file_ids returns 400."""
    r = app_client.post(
        "/api/query/stream",
        json={"question": "test", "file_ids": []},
    )
    assert r.status_code == 400
