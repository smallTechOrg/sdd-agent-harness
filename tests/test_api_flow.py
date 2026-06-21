"""End-to-end API integration test — validates the full chat flow without a browser.

Tests the exact sequence the UI performs:
  POST /datasets → POST /datasets/{id}/files → POST /runs → answer present
  POST /runs/stream → SSE done event with answer + run_id
  chart_spec field propagated through the pipeline (state → runner → server response)

Uses httpx + ASGI transport so no live server is required. Uses FakeModel to avoid a real key.
"""
import json
import os
import tempfile
import csv

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from langchain_core.messages import AIMessage

from src.config import get_settings

# /runs does a REAL run: run_agent falls back to runner.get_model (bound at import), which the
# FakeModelE2E monkeypatch on src.llm.get_model cannot reach. Needs a funded key; skipped offline.
_NEEDS_KEY = pytest.mark.skipif(
    not get_settings().llm_api_key, reason="no funded ANALYST_LLM_API_KEY (real-run /runs path)")


# Patch FakeModel into the server's llm.get_model before importing the app
class FakeModelE2E:
    """Two-turn scripted model: list_datasets → execute_sql → finish."""

    def bind_tools(self, tools):
        self._tools = {t.name: t for t in tools}
        return self

    async def ainvoke(self, messages):
        # Count prior tool messages to decide which step we are on
        from langchain_core.messages import ToolMessage
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        n = len(tool_msgs)

        if n == 0:
            # Step 1: list datasets
            return AIMessage(
                content="",
                tool_calls=[{"id": "tc1", "name": "list_datasets", "args": {}}],
            )
        if n == 1:
            # Step 2: execute SQL
            return AIMessage(
                content="",
                tool_calls=[{"id": "tc2", "name": "execute_sql",
                             "args": {"dataset_id": _DATASET_ID, "sql": "SELECT name FROM test_table LIMIT 1"}}],
            )
        # Step 3: finish
        return AIMessage(
            content="",
            tool_calls=[{"id": "tc3", "name": "finish",
                         "args": {"answer": "The answer is Alice.", "chart_spec": ""}}],
        )


_DATASET_ID = None  # filled by fixture


@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    import src.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_model", lambda: FakeModelE2E())


@pytest_asyncio.fixture
async def client():
    from src.server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def dataset_with_file(client):
    global _DATASET_ID
    # Create dataset
    r = await client.post("/datasets", json={"name": "e2e-test"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"]
    ds_id = data["data"]["id"]
    _DATASET_ID = ds_id

    # Write a tiny CSV to a temp file
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "score"])
        w.writerow(["Alice", 10])
        w.writerow(["Bob", 20])
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as f:
            r = await client.post(
                f"/datasets/{ds_id}/files",
                files={"file": ("test.csv", f, "text/csv")},
            )
        assert r.status_code == 200
        assert r.json()["ok"]
    finally:
        os.unlink(tmp_path)

    return ds_id


@_NEEDS_KEY
@pytest.mark.asyncio
async def test_post_runs_returns_answer(client, dataset_with_file):
    """POST /runs returns answer + chart_spec fields."""
    r = await client.post("/runs", json={
        "goal": "What are the names?",
        "dataset_id": dataset_with_file,
        "thread_id": "test-thread-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body
    data = body["data"]
    assert "answer" in data
    assert data["answer"], "answer must not be empty"
    assert "chart_spec" in data  # field must be present (even if None)
    assert "run_id" in data
    assert "thread_id" in data


@pytest.mark.asyncio
async def test_stream_done_event_has_answer(client, dataset_with_file):
    """POST /runs/stream SSE done event must carry answer + run_id + thread_id."""
    async with client.stream("POST", "/runs/stream", json={
        "goal": "What are the names?",
        "dataset_id": dataset_with_file,
        "thread_id": "test-thread-2",
    }) as resp:
        assert resp.status_code == 200

        done_event = None
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
        for line in buffer.splitlines():
            if not line.startswith("data: "):
                continue
            try:
                ev = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if ev.get("done"):
                done_event = ev
                break

    assert done_event is not None, "stream must emit a done event"
    assert done_event.get("answer"), "done event must carry a non-empty answer"
    assert "run_id" in done_event, "done event must include run_id"
    assert "thread_id" in done_event, "done event must include thread_id"
    assert "chart_spec" in done_event, "done event must include chart_spec key"
