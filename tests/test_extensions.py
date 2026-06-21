"""Step-1 extension tests — DELETE /datasets, GET /audit-log, /health stub_mode, enhanced GET /datasets.

These run fully offline (no API key). Uses FakeModel + ASGI transport (httpx).
"""
import csv
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage


# Patch FakeModel into src.llm before importing the app (same pattern as test_api_flow.py)
class _FakeModelExt:
    """Scripted model: go straight to finish so tests complete in one round-trip."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        from langchain_core.messages import ToolMessage
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if not tool_msgs:
            return AIMessage(
                content="",
                tool_calls=[{"id": "tc1", "name": "finish",
                             "args": {"answer": "42 rows found.", "chart_spec": ""}}],
            )
        # follow-up ainvoke from generate_follow_ups — return a JSON list
        return AIMessage(content='["Question A?", "Question B?", "Question C?"]')


@pytest.fixture(autouse=True)
def patch_model_ext(monkeypatch):
    import src.llm as llm_mod
    monkeypatch.setattr(llm_mod, "get_model", lambda: _FakeModelExt())


@pytest_asyncio.fixture
async def client():
    from src.server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _make_csv() -> str:
    """Write a tiny CSV to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="")
    w = csv.writer(f)
    w.writerow(["city", "pop"])
    w.writerow(["London", 9000000])
    w.writerow(["Paris", 2100000])
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# test_health_includes_stub_mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_includes_stub_mode(client):
    """GET /health must return stub_mode=True and llm_provider from settings."""
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    data = body["data"]
    assert "stub_mode" in data, "health must include stub_mode"
    assert data["stub_mode"] is True, "stub_mode must be True when no API key set"
    assert "llm_provider" in data, "health must include llm_provider"
    assert data["llm_provider"] == "google_genai"


# ---------------------------------------------------------------------------
# test_datasets_enhanced_response
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_datasets_enhanced_response(client):
    """GET /datasets must include row_count, created_at, and tables list."""
    # Upload via convenience endpoint
    tmp = _make_csv()
    try:
        with open(tmp, "rb") as f:
            r = await client.post("/upload", files={"files": ("cities.csv", f, "text/csv")})
        assert r.status_code == 200
        assert r.json()["ok"]
    finally:
        os.unlink(tmp)

    r = await client.get("/datasets")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"]
    datasets = body["data"]
    assert len(datasets) >= 1

    ds = datasets[0]
    assert "row_count" in ds, "row_count must be present"
    assert ds["row_count"] > 0, "row_count must be positive after upload"
    assert "created_at" in ds, "created_at must be present"
    assert "tables" in ds, "tables must be present"
    assert len(ds["tables"]) > 0, "tables must be non-empty"
    tbl = ds["tables"][0]
    assert "table_name" in tbl
    assert "n_rows" in tbl
    assert "columns" in tbl


# ---------------------------------------------------------------------------
# test_delete_dataset_removes_metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_dataset_removes_metadata(client):
    """DELETE /datasets/{id} must remove the dataset from GET /datasets."""
    # Create + upload
    r = await client.post("/datasets", json={"name": "del-test"})
    assert r.json()["ok"]
    ds_id = r.json()["data"]["id"]

    tmp = _make_csv()
    try:
        with open(tmp, "rb") as f:
            r = await client.post(
                f"/datasets/{ds_id}/files",
                files={"file": ("cities.csv", f, "text/csv")},
            )
        assert r.json()["ok"]
    finally:
        os.unlink(tmp)

    # Confirm it exists
    r = await client.get("/datasets")
    ids = [d["id"] for d in r.json()["data"]]
    assert ds_id in ids

    # Delete it
    r = await client.delete(f"/datasets/{ds_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body
    assert body["data"]["deleted"] is True

    # Confirm it's gone
    r = await client.get("/datasets")
    ids_after = [d["id"] for d in r.json()["data"]]
    assert ds_id not in ids_after


@pytest.mark.asyncio
async def test_delete_dataset_not_found(client):
    """DELETE /datasets/{id} for a nonexistent id must return an error."""
    r = await client.delete("/datasets/nonexistent-id-xyz")
    assert r.status_code == 200
    body = r.json()
    assert not body["ok"]
    assert "not found" in body["error"]


# ---------------------------------------------------------------------------
# test_audit_log_returns_entries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_returns_entries(client):
    """Seed a TOOL/execute_sql span directly in the DB and verify GET /audit-log returns it."""
    import time
    from src.db import Run, Span, get_sessionmaker

    # We need a Run row first (FK constraint on spans)
    run_id = "audit-test-run-001"
    now_ms = time.time() * 1000
    async with get_sessionmaker()() as s:
        s.add(Run(id=run_id, goal="test audit goal", status="completed"))
        await s.commit()

    async with get_sessionmaker()() as s:
        s.add(Span(
            id="audit-span-001",
            run_id=run_id,
            name="execute_sql",
            kind="TOOL",
            attributes={"sql": "SELECT * FROM cities", "rows_returned": 2},
            start_ms=now_ms,
            end_ms=now_ms + 15,
            duration_ms=15,
        ))
        await s.commit()

    r = await client.get("/audit-log")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], body
    entries = body["data"]
    assert len(entries) >= 1

    # Find our seeded entry
    found = next((e for e in entries if e["id"] == "audit-span-001"), None)
    assert found is not None, "seeded audit span must appear in /audit-log"
    assert found["duration_ms"] == 15
    assert found["timestamp_ms"] == pytest.approx(now_ms, rel=1e-3)


@pytest.mark.asyncio
async def test_pin_panel_and_get_dashboard(client):
    """POST /dashboard/{session_id}/panels then GET /dashboard/{session_id}."""
    r = await client.post("/dashboard/sess-1/panels", json={
        "session_id": "sess-1", "title": "Revenue by region",
        "query_text": "What is revenue by region?", "answer": "East: $1M, West: $2M",
        "panel_type": "text",
    })
    assert r.status_code == 200 and r.json()["ok"]
    panel_id = r.json()["data"]["id"]

    r2 = await client.get("/dashboard/sess-1")
    assert r2.status_code == 200
    data = r2.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == panel_id
    assert data[0]["title"] == "Revenue by region"


@pytest.mark.asyncio
async def test_remove_panel(client):
    """DELETE /dashboard/{session_id}/panels/{panel_id} removes the panel."""
    r = await client.post("/dashboard/sess-2/panels", json={
        "session_id": "sess-2", "query_text": "test", "answer": "test answer",
    })
    panel_id = r.json()["data"]["id"]
    r2 = await client.delete(f"/dashboard/sess-2/panels/{panel_id}")
    assert r2.status_code == 200 and r2.json()["data"]["deleted"]
    r3 = await client.get("/dashboard/sess-2")
    assert r3.json()["data"] == []


@pytest.mark.asyncio
async def test_remove_panel_wrong_session(client):
    """DELETE with wrong session_id returns error."""
    r = await client.post("/dashboard/sess-3/panels", json={
        "session_id": "sess-3", "query_text": "q", "answer": "a",
    })
    panel_id = r.json()["data"]["id"]
    r2 = await client.delete(f"/dashboard/sess-999/panels/{panel_id}")
    assert not r2.json()["ok"]


@pytest.mark.asyncio
async def test_audit_log_includes_session_id(client):
    """GET /audit-log entries must include session_id (= Run.thread_id) — Gap 1 fix."""
    import time
    from src.db import Run, Span, get_sessionmaker

    run_id = "audit-sid-run-001"
    now_ms = time.time() * 1000
    async with get_sessionmaker()() as s:
        s.add(Run(id=run_id, goal="session-id test", status="completed", thread_id="my-session-xyz"))
        await s.commit()
    async with get_sessionmaker()() as s:
        s.add(Span(
            id="audit-sid-span",
            run_id=run_id, name="execute_sql", kind="TOOL",
            attributes={"sql": "SELECT 1"},
            start_ms=now_ms, end_ms=now_ms + 5, duration_ms=5,
        ))
        await s.commit()

    r = await client.get("/audit-log")
    assert r.status_code == 200
    entries = r.json()["data"]
    found = next((e for e in entries if e["id"] == "audit-sid-span"), None)
    assert found is not None
    assert "session_id" in found, "audit-log entry must include session_id"
    assert found["session_id"] == "my-session-xyz"


@pytest.mark.asyncio
async def test_upload_replace_creates_audit_span(client):
    """Replace-by-name must write a TOOL span visible in GET /audit-log — Gap 2 fix."""
    tmp = _make_csv()
    try:
        with open(tmp, "rb") as f:
            await client.post("/upload", files={"files": ("replace_me.csv", f, "text/csv")})
        with open(tmp, "rb") as f:
            await client.post("/upload", files={"files": ("replace_me.csv", f, "text/csv")})
    finally:
        os.unlink(tmp)

    r = await client.get("/audit-log")
    assert r.status_code == 200
    entries = r.json()["data"]
    replace_entries = [e for e in entries if "replace" in (e.get("sql") or "").lower()
                       or "replace" in str(entries)]
    # Easier: check span table directly via DB
    from src.db import Span, get_sessionmaker
    from sqlalchemy import select
    async with get_sessionmaker()() as s:
        spans = (await s.execute(
            select(Span).where(Span.name == "replace_dataset").where(Span.kind == "TOOL")
        )).scalars().all()
    assert len(spans) >= 1, "replace-by-name must write a TOOL span with name='replace_dataset'"


@pytest.mark.asyncio
async def test_audit_log_since_filter(client):
    """GET /audit-log?since= must exclude older spans."""
    import time
    import datetime
    from src.db import Run, Span, get_sessionmaker

    run_id = "audit-since-run-001"
    old_ms = (time.time() - 3600) * 1000  # 1 hour ago
    async with get_sessionmaker()() as s:
        s.add(Run(id=run_id, goal="since-filter test", status="completed"))
        await s.commit()
    async with get_sessionmaker()() as s:
        s.add(Span(
            id="audit-old-span",
            run_id=run_id,
            name="execute_sql",
            kind="TOOL",
            attributes={"sql": "SELECT 1"},
            start_ms=old_ms,
            end_ms=old_ms + 5,
            duration_ms=5,
        ))
        await s.commit()

    # Filter to "now" — old span should be excluded
    since_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    r = await client.get(f"/audit-log?since={since_str}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"], f"audit-log since filter failed: {body}"
    ids = [e["id"] for e in body["data"]]
    assert "audit-old-span" not in ids, "old span must be filtered out by 'since'"
