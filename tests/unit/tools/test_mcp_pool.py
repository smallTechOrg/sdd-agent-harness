"""Unit tests for the session-scoped MCP pool manager: lazy build, namespacing/routing,
reuse, LRU eviction, and cleanup. Sources are stubbed (no DB) by patching ``_load_sources``;
the MCP servers + DuckDB are exercised for real through the in-memory transport."""
import asyncio

import pandas as pd
import pytest

import data_analysis_agent.tools.mcp.pool as pool_module
from data_analysis_agent.tools.mcp.pool import SessionPoolManager


def _source(tmp_path, name, table, frame):
    pq = tmp_path / f"{table}.parquet"
    pd.DataFrame(frame).to_parquet(pq)
    return {
        "id": table,
        "name": name,
        "table_name": table,
        "parquet_path": str(pq),
        "column_names": list(frame.keys()),
        "capability_description": f"Query {name}",
    }


@pytest.fixture
def patch_sources(monkeypatch):
    """Return a mutable {session_id: [source dict]} map, bypassing the DB."""
    mapping: dict[str, list[dict]] = {}
    monkeypatch.setattr(pool_module, "_load_sources", lambda sid: mapping.get(sid, []))
    return mapping


def test_namespaced_tools_routing_and_schema(tmp_path, patch_sources):
    patch_sources["s1"] = [
        _source(tmp_path, "sales.csv", "ds_sales", {"region": ["N", "S"], "sales": [10, 20]}),
        _source(tmp_path, "cust.csv", "ds_cust", {"name": ["a", "b", "c"]}),
    ]
    mgr = SessionPoolManager(max_pools=8, idle_seconds=1000)

    async def body():
        await mgr.acquire("s1")
        tools, cols = mgr.snapshot("s1")
        sales = await mgr.call_tool("s1", "ds_sales__run_query", {"query": "SELECT SUM(sales) AS s FROM ds_sales"})
        cust = await mgr.call_tool("s1", "ds_cust__run_query", {"query": "SELECT COUNT(*) AS c FROM ds_cust"})
        unknown = await mgr.call_tool("s1", "nope__run_query", {"query": "SELECT 1"})
        return tools, cols, sales, cust, unknown

    tools, cols, sales, cust, unknown = asyncio.run(body())
    assert sorted(t["name"] for t in tools) == ["ds_cust__run_query", "ds_sales__run_query"]
    assert "ds_sales.sales" in cols and "ds_cust.name" in cols
    assert sales == ("s\n30", False)
    assert cust == ("c\n3", False)
    assert unknown[1] is True and "Unknown tool" in unknown[0]


def test_capability_description_becomes_tool_description(tmp_path, patch_sources):
    patch_sources["s1"] = [_source(tmp_path, "sales.csv", "ds_sales", {"sales": [1, 2]})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    tools, _ = mgr.snapshot("s1")
    assert tools[0]["description"] == "Query sales.csv"
    assert "query" in tools[0]["parameter_schema"]


def test_acquire_reuses_the_same_pool(tmp_path, patch_sources):
    patch_sources["s1"] = [_source(tmp_path, "sales.csv", "ds_sales", {"sales": [1, 2]})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        return await mgr.acquire("s1") is await mgr.acquire("s1")

    assert asyncio.run(body()) is True


def test_no_sources_raises(patch_sources):
    mgr = SessionPoolManager(8, 1000)
    with pytest.raises(pool_module.NoDataSourcesError):
        asyncio.run(mgr.acquire("missing"))


def test_lru_eviction_when_over_cap(tmp_path, patch_sources):
    for sid in ("s1", "s2", "s3"):
        patch_sources[sid] = [_source(tmp_path, f"{sid}.csv", f"t_{sid}", {"x": [1, 2]})]
    mgr = SessionPoolManager(max_pools=2, idle_seconds=1000)

    async def body():
        await mgr.acquire("s1")
        await mgr.acquire("s2")
        await mgr.acquire("s3")  # exceeds cap → evicts the LRU (s1)

    asyncio.run(body())
    assert mgr.snapshot("s1") == ([], [])  # evicted
    assert mgr.snapshot("s2")[0]           # still cached
    assert mgr.snapshot("s3")[0]


def test_close_is_idempotent(tmp_path, patch_sources):
    patch_sources["s1"] = [_source(tmp_path, "sales.csv", "ds_sales", {"sales": [1, 2]})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    mgr.close("s1")
    mgr.close("s1")  # must not raise
    assert mgr.snapshot("s1") == ([], [])
