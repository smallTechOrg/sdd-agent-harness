"""Unit tests for the 5-stage sync pipeline (stub mode): generation of tools/resources/prompts,
version bump, soft-delete of dropped capabilities, and stub coverage of every stage tag."""
import datetime as _dt

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_analysis_agent.db.models import Base, McpPromptRow, McpResourceRow, DatabaseRow, McpToolRow
from data_analysis_agent.tools.sync import (
    ValidationError,
    add_prompt,
    add_resource,
    add_tool,
    apply_sync_result,
    delete_prompt,
    delete_resource,
    delete_tool,
    run_sync,
    update_resource,
    update_tool,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/sync.db")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


@pytest.fixture(autouse=True)
def _stub(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAANALYSIS_OPENROUTER_API_KEY", "")
    monkeypatch.setenv("DATAANALYSIS_DATASETS_DIR", str(tmp_path / "datasets"))
    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None
    yield
    llm_module._client = None


def _server(db, tmp_path, name="sales") -> DatabaseRow:
    """Create a parquet database whose table the connector will discover from its datasets directory."""
    from data_analysis_agent.tools.table_naming import sql_table_name
    directory = tmp_path / "datasets" / sql_table_name(name)
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": [1, 2, 3], "amount": [5, 7, 3]}).to_parquet(directory / "orders.parquet")
    srv = DatabaseRow(name=name, type="parquet", uri=f"parquet:///{name}")
    db.add(srv)
    db.flush()
    return srv


def _discovered_tables(srv) -> list[str]:
    """Table names the connector inspects from the database's directory."""
    from data_analysis_agent.tools.connectors.base import get_connector
    conn = get_connector({"id": srv.id, "name": srv.name, "type": srv.type, "uri": srv.uri})
    return [t["table_name"] for t in conn.discover_tables()]


def _active(db, model, database_id):
    return db.query(model).filter_by(database_id=database_id, deleted_at=None).all()


def test_run_sync_generates_capabilities(db, tmp_path):
    srv = _server(db, tmp_path)
    apply_sync_result(db, srv, run_sync(db, srv))
    db.commit()
    assert srv.version == 2 and srv.title and srv.description
    assert srv.last_sync_status == "ok"
    tools = _active(db, McpToolRow, srv.id)
    resources = _active(db, McpResourceRow, srv.id)
    prompts = _active(db, McpPromptRow, srv.id)
    assert len(tools) >= 1 and len(prompts) >= 1
    assert any(r.kind == "schema" for r in resources)   # the dataset schema resource
    # the generated tool's SQL must compile (validated at apply)
    assert all(t.sql_template.upper().startswith("SELECT") for t in tools)


def test_resync_soft_deletes_dropped_tool(db, tmp_path):
    srv = _server(db, tmp_path)
    apply_sync_result(db, srv, run_sync(db, srv))
    db.commit()
    # Inject an extra active tool the next sync won't propose; it must be SOFT-deleted, not removed.
    orphan = McpToolRow(database_id=srv.id, name="orphan_tool", description="x", created_version=srv.version)
    orphan.execution = {"sql_template": "SELECT 1", "parameters": []}
    db.add(orphan)
    db.commit()
    apply_sync_result(db, srv, run_sync(db, srv))
    db.commit()
    refreshed = db.get(McpToolRow, orphan.id)
    assert refreshed.deleted_at is not None        # soft-deleted (never hard-deleted)
    assert db.get(McpToolRow, orphan.id) is not None  # row still exists


def _synced(db, tmp_path):
    srv = _server(db, tmp_path)
    apply_sync_result(db, srv, run_sync(db, srv))
    db.commit()
    return srv


def _tombstoned(db, model, database_id):
    return db.query(model).filter(model.database_id == database_id, model.deleted_at.isnot(None)).count()


_OK_TOOL = {"name": "top_orders", "description": "top",
            "sql_template": "SELECT * FROM orders LIMIT 5",
            "input_schema": {"type": "object", "properties": {}}}


def test_add_tool_cascades_prompts_additively(db, tmp_path):
    srv = _synced(db, tmp_path)
    v0 = srv.version
    add_tool(db, srv, _OK_TOOL)
    db.commit()
    assert srv.version == v0 + 1
    tools = {t.name for t in _active(db, McpToolRow, srv.id)}
    assert "top_orders" in tools and "list_orders" in tools          # additive: old tool kept
    prompts = {p.name for p in _active(db, McpPromptRow, srv.id)}
    assert "explore_top_orders" in prompts                            # cascaded prompt for the new tool
    assert _tombstoned(db, McpToolRow, srv.id) == 0                   # cascade never soft-deletes
    assert _tombstoned(db, McpPromptRow, srv.id) == 0


def test_add_tool_single_version_bump(db, tmp_path):
    srv = _synced(db, tmp_path)
    v0 = srv.version
    add_tool(db, srv, _OK_TOOL)
    db.commit()
    assert srv.version == v0 + 1
    tool = next(t for t in _active(db, McpToolRow, srv.id) if t.name == "top_orders")
    prompt = next(p for p in _active(db, McpPromptRow, srv.id) if p.name == "explore_top_orders")
    assert tool.created_version == srv.version == prompt.created_version  # one version across add+cascade


def test_add_tool_rejects_active_duplicate(db, tmp_path):
    srv = _synced(db, tmp_path)
    add_tool(db, srv, _OK_TOOL)
    db.commit()
    with pytest.raises(ValidationError):
        add_tool(db, srv, _OK_TOOL)        # duplicate active name
    db.rollback()


def test_update_tool_requires_existing(db, tmp_path):
    srv = _synced(db, tmp_path)
    with pytest.raises(ValidationError):
        update_tool(db, srv, {"name": "does_not_exist", "sql_template": "SELECT 1"})
    db.rollback()


def test_add_tool_rejects_bad_sql(db, tmp_path):
    srv = _synced(db, tmp_path)
    for bad in (
        {"name": "a", "sql_template": "DELETE FROM orders"},                    # non-SELECT
        {"name": "b", "sql_template": "SELECT 1; DROP TABLE orders"},           # multi-statement
        {"name": "c", "sql_template": "SELECT * FROM orders WHERE id > $x"},    # undeclared $param
    ):
        with pytest.raises(ValidationError):
            add_tool(db, srv, bad)
        db.rollback()


def test_add_prompt_has_no_cascade(db, tmp_path):
    srv = _synced(db, tmp_path)
    tools_before = {t.name for t in _active(db, McpToolRow, srv.id)}
    add_prompt(db, srv, {"name": "my_custom", "description": "mine"})
    db.commit()
    assert "my_custom" in {p.name for p in _active(db, McpPromptRow, srv.id)}
    assert {t.name for t in _active(db, McpToolRow, srv.id)} == tools_before  # tools untouched


def test_cascade_preserves_manually_added_prompt(db, tmp_path):
    srv = _synced(db, tmp_path)
    add_prompt(db, srv, {"name": "my_custom", "description": "mine"})
    db.commit()
    add_tool(db, srv, _OK_TOOL)            # cascades prompts (additively)
    db.commit()
    prompts = {p.name for p in _active(db, McpPromptRow, srv.id)}
    assert "my_custom" in prompts          # additive cascade must NOT soft-delete a manual prompt
    assert "explore_top_orders" in prompts


def test_add_resource_bumps_version_and_keeps_siblings(db, tmp_path):
    srv = _synced(db, tmp_path)
    v0 = srv.version
    tools_before = {t.name for t in _active(db, McpToolRow, srv.id)}
    add_resource(db, srv, {"uri": "entity://sales/foo", "name": "foo", "kind": "primary_entity"})
    db.commit()
    assert srv.version == v0 + 1
    assert "entity://sales/foo" in {r.uri for r in _active(db, McpResourceRow, srv.id)}
    # a pure entity (no physical table) adds no tool, and the cascade never drops existing tools
    assert {t.name for t in _active(db, McpToolRow, srv.id)} == tools_before
    assert _tombstoned(db, McpToolRow, srv.id) == 0


def test_add_tool_rejects_file_reading_functions(db, tmp_path):
    srv = _synced(db, tmp_path)
    for bad in (
        {"name": "leak", "sql_template": "SELECT content FROM read_text('/etc/passwd')"},
        {"name": "leak2", "sql_template": "SELECT * FROM read_csv('/etc/hosts')"},
        # parameterized path skips the compile-check but the guard must still block the function
        {"name": "leak3", "sql_template": "SELECT * FROM read_blob($p)",
         "input_schema": {"type": "object", "properties": {"p": {"type": "string"}}}},
    ):
        with pytest.raises(ValidationError):
            add_tool(db, srv, bad)
        db.rollback()


def test_update_tool_is_patch_not_replace(db, tmp_path):
    srv = _synced(db, tmp_path)
    tool = _active(db, McpToolRow, srv.id)[0]
    original_sql = tool.sql_template
    update_tool(db, srv, {"name": tool.name, "description": "updated desc only"})
    db.commit()
    refreshed = next(t for t in _active(db, McpToolRow, srv.id) if t.name == tool.name)
    assert refreshed.description == "updated desc only"
    assert refreshed.sql_template == original_sql        # omitted field preserved (patch, not replace)


def test_schema_resource_cannot_be_added_or_deleted_but_can_be_updated(db, tmp_path):
    srv = _synced(db, tmp_path)
    schema_uri = f"dataset://{srv.name}/schema"
    # add of a schema-kind resource is rejected (tied to the server's existence)
    with pytest.raises(ValidationError):
        add_resource(db, srv, {"uri": "entity://x/y", "name": "y", "kind": "schema"})
    db.rollback()
    # delete of the schema resource is rejected
    with pytest.raises(ValidationError):
        delete_resource(db, srv, schema_uri)
    db.rollback()
    # but manual update of its relationships IS allowed
    update_resource(db, srv, {"uri": schema_uri,
                              "content": {"relationships": [{"from": "orders", "to": "x", "on": "id"}]}})
    db.commit()
    schema_res = next(r for r in _active(db, McpResourceRow, srv.id) if r.kind == "schema")
    rels = schema_res.content["relationships"]               # canonical FK-edge list on the schema resource
    assert rels and rels[0]["from_table"] == "orders" and rels[0]["to_table"] == "x"
    assert "tables" not in schema_res.content               # NOT per-table columns


def test_delete_tool_hard_deletes_and_prunes_prompts(db, tmp_path):
    srv = _synced(db, tmp_path)
    add_tool(db, srv, _OK_TOOL)
    db.commit()
    assert "explore_top_orders" in {p.name for p in _active(db, McpPromptRow, srv.id)}
    tool = next(t for t in _active(db, McpToolRow, srv.id) if t.name == "top_orders")
    tool_id = tool.id
    delete_tool(db, srv, "top_orders")
    db.commit()
    assert db.get(McpToolRow, tool_id) is None                       # HARD delete (manual) — row gone
    assert "top_orders" not in {t.name for t in _active(db, McpToolRow, srv.id)}
    assert "explore_top_orders" not in {p.name for p in _active(db, McpPromptRow, srv.id)}  # pruned cascade


def test_delete_prompt_hard_deletes_no_cascade(db, tmp_path):
    srv = _synced(db, tmp_path)
    add_prompt(db, srv, {"name": "my_custom", "description": "mine"})
    db.commit()
    pid = next(p.id for p in _active(db, McpPromptRow, srv.id) if p.name == "my_custom")
    tools_before = {t.name for t in _active(db, McpToolRow, srv.id)}
    delete_prompt(db, srv, "my_custom")
    db.commit()
    assert db.get(McpPromptRow, pid) is None                         # hard delete
    assert {t.name for t in _active(db, McpToolRow, srv.id)} == tools_before  # leaf — no cascade


def test_delete_resource_drops_table_and_regenerates(db, tmp_path):
    srv = _synced(db, tmp_path)
    entity_uri = f"entity://{srv.name}/orders"
    assert "orders" in _discovered_tables(srv)
    delete_resource(db, srv, entity_uri)
    db.commit()
    # backing table file dropped (re-inspection finds nothing) + the entity resource gone
    assert "orders" not in _discovered_tables(srv)
    assert entity_uri not in {r.uri for r in _active(db, McpResourceRow, srv.id)}
    # tools that referenced the dropped table are pruned (regenerated against remaining tables)
    assert "list_orders" not in {t.name for t in _active(db, McpToolRow, srv.id)}
    assert any(r.kind == "schema" for r in _active(db, McpResourceRow, srv.id))  # schema resource survives


def test_tool_execution_object_is_stored_and_derived(db, tmp_path):
    srv = _synced(db, tmp_path)
    add_tool(db, srv, {
        "name": "by_amount", "description": "filter",
        "execution": {"sql_template": "SELECT * FROM orders WHERE amount > $min",
                      "parameters": [{"name": "min", "type": "integer"}]},
    })
    db.commit()
    tool = next(t for t in _active(db, McpToolRow, srv.id) if t.name == "by_amount")
    assert tool.execution["sql_template"].startswith("SELECT")
    assert tool.execution["parameters"][0] == {"name": "min", "type": "integer"}
    assert tool.input_schema["properties"]["min"]["type"] == "integer"   # derived MCP inputSchema


def test_entities_are_exactly_the_inspected_tables(db, tmp_path):
    from data_analysis_agent.tools.table_naming import sql_table_name
    srv = _server(db, tmp_path)  # writes orders.parquet
    directory = tmp_path / "datasets" / sql_table_name(srv.name)
    pd.DataFrame({"customer_id": [10, 20], "region": ["N", "S"]}).to_parquet(directory / "customers.parquet")
    apply_sync_result(db, srv, run_sync(db, srv))
    db.commit()
    entity_names = sorted(r.name for r in _active(db, McpResourceRow, srv.id) if r.kind != "schema")
    assert entity_names == sorted(_discovered_tables(srv)) == ["customers", "orders"]  # definite, 1 per table
    orders = next(r for r in _active(db, McpResourceRow, srv.id) if r.name == "orders")
    assert [c["name"] for c in orders.content["columns"]] == ["id", "amount"]  # columns from inspection


def test_entity_resource_carries_columns_and_size(db, tmp_path):
    srv = _synced(db, tmp_path)
    entity = next(r for r in _active(db, McpResourceRow, srv.id) if r.kind != "schema")
    assert entity.content["table"] == "orders"
    assert any(c.get("name") == "id" for c in entity.content["columns"])  # per-table columns live here
    assert entity.size and entity.size > 0                                # backing parquet file size


def test_stub_handles_all_node_tags():
    from data_analysis_agent.llm.providers.stub import StubLLMProvider
    stub = StubLLMProvider()
    tags = ["<node:plan_action>", "<node:sync_title>", "<node:sync_schema>",
            "<node:sync_entities>", "<node:sync_tools>", "<node:sync_prompts>"]
    for tag in tags:
        out = stub.complete(f"{tag}\nDataset name: d\nTable: t\nTables available: t\nTool: list_t").text
        assert "unrecognized node tag" not in out, f"{tag} not handled by stub"
