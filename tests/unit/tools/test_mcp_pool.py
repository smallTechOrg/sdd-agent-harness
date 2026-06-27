"""Unit tests for the session pool: flat snapshot, server routing, within-server JOINs, reuse, LRU
eviction, cleanup, and Phase-B hybrid routing (generated GET-API tools via optional `capability`).
Servers are stubbed (no DB) by patching ``_load_databases``; the in-process MCP servers + DuckDB are real."""
import asyncio

import pandas as pd
import pytest

import data_analysis_agent.tools.mcp.pool as pool_module
from data_analysis_agent.tools.mcp.pool import SessionPoolManager


@pytest.fixture(autouse=True)
def _datasets_dir(monkeypatch, tmp_path):
    """Point the connector's inspection at this test's datasets directory."""
    monkeypatch.setenv("DATAANALYSIS_DATASETS_DIR", str(tmp_path / "datasets"))


def _server(tmp_path, name, tables_spec, gen_tools=None):
    """Build a ``(server_dict, tables, gen_tools)`` triple (tables in the resources/`discover` shape).

    Writes the Parquet files at the canonical location so ``build_server(table_names)`` registers them.
    ``tables`` stands in for what ``active_entity_tables`` would return from the resources table.
    """
    from data_analysis_agent.tools.table_naming import sql_table_name
    directory = tmp_path / "datasets" / sql_table_name(name)
    directory.mkdir(parents=True, exist_ok=True)
    tables = []
    for table_name, frame in tables_spec.items():
        pd.DataFrame(frame).to_parquet(directory / f"{table_name}.parquet")
        tables.append({"table_name": table_name, "column_names": list(frame.keys()),
                       "schema": [{"name": c} for c in frame], "row_count": len(next(iter(frame.values())))})
    server = {"id": name, "name": name, "type": "parquet", "uri": f"parquet:///{name}",
              "description": f"Server {name}"}
    return server, tables, gen_tools or []


@pytest.fixture
def patch_servers(monkeypatch):
    """Return a mutable {session_id: [(server, tables, gen_tools), ...]} map, bypassing the DB."""
    mapping: dict[str, list] = {}
    monkeypatch.setattr(pool_module, "_load_databases", lambda sid: mapping.get(sid, []))
    return mapping


def test_snapshot_flat_and_single_level_routing(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "sales_db", {
        "orders": {"id": [1, 2, 3], "cust": [10, 10, 20], "amount": [5, 7, 3]},
        "customers": {"id": [10, 20], "region": ["N", "S"]},
    })]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        snap = mgr.snapshot("s1")
        ok = await mgr.call_tool("s1", "sales_db", {
            "query": "SELECT c.region, SUM(o.amount) AS t FROM orders o JOIN customers c "
                     "ON o.cust = c.id GROUP BY c.region ORDER BY c.region"
        })
        bad = await mgr.call_tool("s1", "nope", {"query": "SELECT 1"})
        return snap, ok, bad

    snap, ok, bad = asyncio.run(body())
    assert len(snap) == 1 and snap[0]["tool"] == "sales_db"
    assert sorted(t["table"] for t in snap[0]["tables"]) == ["customers", "orders"]
    assert snap[0]["capabilities"] == []                  # no generated tools
    assert ok == ("region,t\nN,12\nS,3", False)            # within-server JOIN
    assert bad[1] is True and "Unknown tool" in bad[0]


def test_snapshot_carries_tables_and_columns(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "d", {"orders": {"id": [1], "total": [5]}})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    snap = mgr.snapshot("s1")[0]
    assert snap["description"] == "Server d"
    assert snap["tables"][0] == {"table": "orders", "columns": ["id", "total"]}


def test_pool_never_inspects_the_store(tmp_path, patch_servers, monkeypatch):
    """The pool builds + queries entirely from the resources table — it must NOT call discover_tables."""
    import data_analysis_agent.tools.connectors.parquet as parquet_mod
    monkeypatch.setattr(parquet_mod.ParquetConnector, "discover_tables",
                        lambda self: (_ for _ in ()).throw(AssertionError("pool inspected the store!")))
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A", "B"], "n": [1, 2]}})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "shop", {"query": "SELECT COUNT(*) AS c FROM products"})

    text, is_error = asyncio.run(body())
    assert is_error is False and text.strip() == "c\n2"   # built + queried with no discover_tables call


def test_non_select_is_recoverable_error(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "d", {"query": "DROP TABLE t"})

    text, is_error = asyncio.run(body())
    assert is_error is True and "SELECT" in text


# --- Phase B: hybrid generated-tool routing ---------------------------------

def _gen_tool(name, sql, params=None):
    props = {p: {"type": "integer"} for p in (params or [])}
    return {"name": name, "description": f"gen {name}", "sql_template": sql,
            "input_schema": {"type": "object", "properties": props}}


def test_snapshot_includes_capabilities(tmp_path, patch_servers):
    gt = [_gen_tool("top_products", "SELECT name FROM products WHERE revenue > $min", ["min"])]
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A", "B"], "revenue": [100, 50]}}, gt)]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    caps = mgr.snapshot("s1")[0]["capabilities"]
    assert caps and caps[0]["name"] == "top_products" and caps[0]["params"] == ["min"]


def test_call_generated_tool_binds_params(tmp_path, patch_servers):
    gt = [_gen_tool("top_products", "SELECT name FROM products WHERE revenue > $min ORDER BY name", ["min"])]
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A", "B"], "revenue": [100, 50]}}, gt)]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "shop", {"min": 60}, capability="top_products")

    text, is_error = asyncio.run(body())
    assert is_error is False
    assert text.strip() == "name\nA"                       # only revenue>60 → A; param bound


def test_capability_absent_runs_free_sql(tmp_path, patch_servers):
    gt = [_gen_tool("noop", "SELECT 1 AS x")]
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A"]}}, gt)]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "shop", {"query": "SELECT COUNT(*) AS c FROM products"})

    assert asyncio.run(body()) == ("c\n1", False)           # free SQL still routes to generic tool


def test_unknown_capability_is_recoverable(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A"]}}, [_gen_tool("x", "SELECT 1")])]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "shop", {}, capability="nope")

    text, is_error = asyncio.run(body())
    assert is_error is True and "Unknown capability" in text and "free SQL" in text


def test_free_sql_blocks_file_reading_functions(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "d", {"query": "SELECT * FROM read_text('/etc/hosts')"})

    text, is_error = asyncio.run(body())
    assert is_error is True and "Disallowed function" in text   # arbitrary file read blocked


def test_generated_tool_blocks_non_select(tmp_path, patch_servers):
    gt = [_gen_tool("danger", "DROP TABLE products")]
    patch_servers["s1"] = [_server(tmp_path, "shop", {"products": {"name": ["A"]}}, gt)]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        await mgr.acquire("s1")
        return await mgr.call_tool("s1", "shop", {}, capability="danger")

    text, is_error = asyncio.run(body())
    assert is_error is True and "SELECT" in text            # read-only guard runs on generated tools too


# --- lifecycle (unchanged from Phase A) -------------------------------------

def test_acquire_reuses_pool(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)

    async def body():
        return await mgr.acquire("s1") is await mgr.acquire("s1")

    assert asyncio.run(body()) is True


def test_no_servers_raises(patch_servers):
    mgr = SessionPoolManager(8, 1000)
    with pytest.raises(pool_module.NoServersError):
        asyncio.run(mgr.acquire("missing"))


def test_lru_eviction(tmp_path, patch_servers):
    for sid in ("s1", "s2", "s3"):
        patch_servers[sid] = [_server(tmp_path, f"d_{sid}", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(max_pools=2, idle_seconds=1000)

    async def body():
        await mgr.acquire("s1")
        await mgr.acquire("s2")
        await mgr.acquire("s3")  # exceeds cap → evicts LRU (s1)

    asyncio.run(body())
    assert mgr.snapshot("s1") == []   # evicted
    assert mgr.snapshot("s2") and mgr.snapshot("s3")


def test_close_is_idempotent(tmp_path, patch_servers):
    patch_servers["s1"] = [_server(tmp_path, "d", {"t": {"x": [1]}})]
    mgr = SessionPoolManager(8, 1000)
    asyncio.run(mgr.acquire("s1"))
    mgr.close("s1")
    mgr.close("s1")  # must not raise
    assert mgr.snapshot("s1") == []
