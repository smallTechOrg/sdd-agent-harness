import csv
import datetime
import io
import uuid

import aiosqlite
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Isolated client with its own SQLite + DuckDB files and bootstrapped tables."""
    monkeypatch.setenv("DAA_SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("DAA_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    from src.config import get_settings
    get_settings.cache_clear()

    from src.api.main import create_app
    import src.api.main as main_mod

    app = create_app()

    # lifespan not triggered by ASGITransport — bootstrap manually
    from src.db.sqlite import create_tables_sqlite
    await create_tables_sqlite()
    main_mod._ready = True

    ac = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield ac
    await ac.aclose()
    main_mod._ready = False
    get_settings.cache_clear()


async def _insert_session(session_id: str) -> None:
    """Insert a session row directly; avoids depending on Step 2B sessions endpoint."""
    from src.config import get_settings
    now = datetime.datetime.now(datetime.UTC).isoformat()
    async with aiosqlite.connect(get_settings().sqlite_path) as db:
        await db.execute(
            "INSERT INTO session (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, "Test Session", now, now),
        )
        await db.commit()


def _make_csv_bytes(rows: int = 100) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["product", "revenue", "category"])
    products = [f"Widget {chr(65 + i)}" for i in range(10)]
    revenues = [5000, 4200, 3800, 3100, 2900, 2400, 2000, 1700, 1400, 1100]
    categories = ["Electronics", "Clothing", "Food"]
    for i in range(rows):
        idx = i % 10
        writer.writerow([products[idx], revenues[idx] + (i % 3) * 10, categories[i % 3]])
    return buf.getvalue().encode()


@pytest.mark.asyncio
async def test_upload_and_list(client):
    """P1-AC4: upload 100-row CSV, GET /datasets returns name, row_count, file_format."""
    session_id = str(uuid.uuid4())
    await _insert_session(session_id)

    csv_bytes = _make_csv_bytes(100)
    r = await client.post(
        f"/datasets?session_id={session_id}",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "sample.csv"
    assert data["row_count"] == 100
    assert data["file_format"] == "csv"
    assert len(data["column_schema"]) == 3

    r2 = await client.get(f"/datasets?session_id={session_id}")
    assert r2.status_code == 200, r2.text
    datasets = r2.json()["datasets"]
    assert any(
        d["name"] == "sample.csv" and d["row_count"] == 100 and d["file_format"] == "csv"
        for d in datasets
    )


@pytest.mark.asyncio
async def test_upload_unsupported_file(client):
    """P1-AC5: unsupported file type returns 422 with error.code == UNSUPPORTED_FILE."""
    session_id = str(uuid.uuid4())
    await _insert_session(session_id)

    r = await client.post(
        f"/datasets?session_id={session_id}",
        files={"file": ("broken.png", b"\x89PNG\r\n", "image/png")},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "UNSUPPORTED_FILE"


@pytest.mark.asyncio
async def test_upload_no_session(client):
    """POST /datasets with unknown session_id → 404 NO_SESSION."""
    fake_session = str(uuid.uuid4())
    csv_bytes = _make_csv_bytes(5)
    r = await client.post(
        f"/datasets?session_id={fake_session}",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NO_SESSION"


@pytest.mark.asyncio
async def test_list_no_session(client):
    """GET /datasets with unknown session_id → 404 NO_SESSION."""
    r = await client.get(f"/datasets?session_id={uuid.uuid4()}")
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NO_SESSION"


@pytest.mark.asyncio
async def test_upload_duckdb_table_persisted(client, tmp_path):
    """DuckDB table actually exists after upload — not a view [C-DUCKDB-VIEW]."""
    import duckdb
    from src.config import get_settings

    session_id = str(uuid.uuid4())
    await _insert_session(session_id)

    csv_bytes = _make_csv_bytes(10)
    r = await client.post(
        f"/datasets?session_id={session_id}",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 201, r.text
    table_name = r.json()["duckdb_table"]

    # Open a fresh DuckDB connection and verify the table holds data
    con = duckdb.connect(get_settings().duckdb_path)
    try:
        result = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        assert result[0] == 10
    finally:
        con.close()
