import os
import subprocess
import sys

import aiosqlite
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_health_after_bootstrap():
    """P1-AC2 / P1-AC7 — health returns 200 with stub_mode:true after bootstrap.

    httpx ASGITransport does not trigger ASGI lifespan automatically, so we
    bootstrap SQLite and flip _ready manually — exactly what lifespan does.
    """
    import src.api.main as main_module
    from src.db.sqlite import create_tables_sqlite
    from src.api.main import create_app

    await create_tables_sqlite()
    main_module._ready = True
    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            r = await ac.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["stub_mode"] is True
    finally:
        main_module._ready = False


@pytest.mark.asyncio
async def test_tables_created(tmp_path, monkeypatch):
    """All 5 tables exist after create_tables_sqlite()."""
    monkeypatch.setenv("DAA_SQLITE_PATH", str(tmp_path / "test.db"))
    from src.config import get_settings
    get_settings.cache_clear()
    try:
        from src.db.sqlite import create_tables_sqlite
        await create_tables_sqlite()
        expected = {"session", "dataset", "query_run", "conversation_message", "audit_log"}
        async with aiosqlite.connect(str(tmp_path / "test.db")) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            found = {row[0] async for row in cursor}
        assert expected.issubset(found), f"Missing tables: {expected - found}"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_refuse_to_start_without_key(tmp_path):
    """P1-AC6 — server refuses to start when provider=gemini and key absent."""
    env = {
        "DAA_LLM_PROVIDER": "gemini",
        "DAA_DUCKDB_PATH": str(tmp_path / "x.duckdb"),
        "DAA_SQLITE_PATH": str(tmp_path / "x.db"),
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import asyncio; "
                "from contextlib import asynccontextmanager; "
                "from src.api.main import create_app; "
                "app = create_app(); "
                "from src.api.main import lifespan; "
                "asyncio.run(lifespan(app).__aenter__())"
            ),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        cwd="/Users/sai/Workspace/Code/ai-spec-driven-boilerplate",
    )
    combined = result.stdout + result.stderr
    assert "DAA_GEMINI_API_KEY" in combined or result.returncode != 0, (
        f"Expected refusal but got: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
