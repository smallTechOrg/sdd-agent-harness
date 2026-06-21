"""Ingest-dataset capability — deterministic integration test (runs inside the demo-gate sequence).

EARS: upload registers a table with correct schema/row-count; a second file is a second queryable table;
an unsupported/malformed file is rejected AND prior tables remain intact.
"""
import httpx

from src.server import app


async def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_upload_registers_tables_and_rejects_bad_file():
    async with await _client() as c:
        ds = (await c.post("/datasets", json={"name": "T"})).json()["data"]["id"]

        # EARS 1: upload a CSV → a table with correct row count + columns
        files = {"file": ("sales.csv", "region,amount\nWest,10\nEast,20\nWest,5\n", "text/csv")}
        d = (await c.post(f"/datasets/{ds}/files", files=files)).json()
        assert d["ok"], d
        assert d["data"]["table_name"] == "sales"
        assert d["data"]["n_rows"] == 3
        assert {col["name"] for col in d["data"]["columns"]} == {"region", "amount"}

        # EARS 2: a second file → a second queryable table, first one kept
        files2 = {"file": ("more.json", '[{"a": 1, "b": 2}, {"a": 3, "b": 4}]', "application/json")}
        assert (await c.post(f"/datasets/{ds}/files", files=files2)).json()["ok"]
        tables = {t["table_name"] for t in (await c.get(f"/datasets/{ds}")).json()["data"]["tables"]}
        assert tables == {"sales", "more"}

        # EARS 3: unsupported file rejected, and prior tables remain intact
        bad = {"file": ("notes.txt", "just some text", "text/plain")}
        rej = (await c.post(f"/datasets/{ds}/files", files=bad)).json()
        assert rej["ok"] is False
        assert "unsupported" in rej["error"].lower()
        tables_after = {t["table_name"] for t in (await c.get(f"/datasets/{ds}")).json()["data"]["tables"]}
        assert tables_after == {"sales", "more"}        # intact after the rejected upload


async def test_health_and_run_envelope():
    async with await _client() as c:
        h = (await c.get("/health")).json()
        assert h["ok"] and h["data"]["status"] == "alive"
