"""Sync orchestration.

- Full sync (`run_sync` + `apply_sync_result`): regenerate all 5 stages and **soft-delete** dropped
  capabilities (the only pruning operation).
- Partial sync (`apply_partial` + the six `add_*`/`update_*` ops): apply ONE client-supplied capability,
  then run an **ADDITIVE** cascade of the downstream stages — insert/update only, never soft-delete a
  sibling. One transaction, one version bump.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy.orm import Session

from data_analysis_agent.db.models import (
    McpPromptRow,
    McpResourceRow,
    DatabaseRow,
    McpToolRow,
)
from data_analysis_agent.tools.connectors.base import get_connector
from data_analysis_agent.tools.mcp.server import (
    RecoverableQueryError,
    _guard_select,
    _run_select_params,
)
from data_analysis_agent.tools.sync import stages

log = structlog.get_logger()

_PARAM = re.compile(r"\$(\w+)")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _server_dict(server: DatabaseRow) -> dict:
    return {"id": server.id, "name": server.name, "type": server.type, "uri": server.uri}


def _connector(server: DatabaseRow):
    """The database's connector — inspects tables (sync) and builds the query server over named tables."""
    return get_connector(_server_dict(server))


def _discover_relationships(connector) -> list[dict]:
    """Foreign-key relationships from inspection, when the connector exposes them (else ``[]``)."""
    try:
        return connector.discover_relationships() or []
    except Exception:
        return []


def _entities_from_inspection(database_name: str, tables: list[dict], llm_entities: list[dict]) -> list[dict]:
    """Build one entity per **inspected** table (definite); take only title/description from the LLM.

    The set of entities is the connector's inspected tables — the LLM never invents or drops one. The
    LLM's per-table title/description is used as backfill, with a deterministic default otherwise.
    """
    by_name = {e.get("name"): e for e in (llm_entities or [])}
    entities: list[dict] = []
    for t in tables:
        tname = t["table_name"]
        e = by_name.get(tname) or {}
        entities.append({
            "name": tname,
            "title": e.get("title") or tname.replace("_", " ").title(),
            "description": e.get("description") or f"The '{tname}' entity.",
            "kind": e.get("kind") or "primary_entity",
            "uri": f"entity://{database_name}/{tname}",
            "mime_type": "application/json",
        })
    return entities


class ValidationError(Exception):
    """A client-supplied capability definition is invalid (surfaced as JSON-RPC -32602)."""


@dataclass
class SyncResult:
    """The capabilities a full sync run proposes for a server."""

    title: str
    description: str
    dataset_schema: dict
    resources: list[dict]
    tools: list[dict]
    prompts: list[dict]
    status: str  # "ok" | "partial"


@dataclass
class CascadeFlags:
    """Which downstream stages a mutation must regenerate (additively), in dependency order."""

    tools: bool = False
    prompts: bool = False


@dataclass
class PartialResult:
    """Outcome of a single granular mutation + its additive cascade."""

    child: str
    op: str
    key: str
    tools_changed: bool
    prompts_changed: bool
    status: str


# --- Full sync (run + apply) ------------------------------------------------

def run_sync(db: Session, server: DatabaseRow) -> SyncResult:
    """Run the 5 LLM stages over the database's tables + existing capabilities. Never raises.

    Physical tables are **inspected live via the connector** (no stored catalog) — the connector knows
    the database type and how to introspect it.
    """
    name = server.name
    connector = _connector(server)
    tables = connector.discover_tables()   # the ONLY inspection of the underlying store (sync only)
    active = _active(db, server.id)

    td = stages.stage_title(name, tables, {"title": server.title, "description": server.description})
    # Entities are DEFINITE — exactly the inspected tables. The LLM only backfills title/description.
    entities = _entities_from_inspection(
        name, tables, stages.stage_entities(name, tables, _meta(active["resources"], "uri", "name")))
    # Relationships come from inspection when the connector exposes FKs; otherwise the LLM backfills them.
    conn_rels = _discover_relationships(connector)
    schema = ({"relationships": conn_rels} if conn_rels
              else stages.stage_schema(name, tables, _active_schema_content(active["resources"])))
    tools = stages.stage_tools(name, entities, tables, _meta(active["tools"], "name"))
    prompts = stages.stage_prompts(name, tools, _meta(active["prompts"], "name"))

    tools, dropped = _validate_tools(server, connector, [t["table_name"] for t in tables], tools)
    tables_by_name = {t["table_name"]: t for t in tables}
    resources = [_schema_resource(name, schema)] + [
        _entity_resource(name, e, tables_by_name) for e in entities
    ]
    status = "partial" if dropped else "ok"
    log.info("sync.run", server=name, tools=len(tools), resources=len(resources), prompts=len(prompts),
             status=status)
    return SyncResult(td["title"], td["description"], schema, resources, tools, prompts, status)


def apply_sync_result(db: Session, server: DatabaseRow, result: SyncResult) -> None:
    """Apply a full :class:`SyncResult`: insert/update/soft-delete children + bump version once."""
    new_version = (server.version or 1) + 1
    _apply_all(db, server, new_version, result)
    server.version = new_version
    server.title = result.title
    server.description = result.description
    server.last_synced_at = _now()
    server.last_sync_status = result.status


def _apply_all(db: Session, server: DatabaseRow, new_version: int, result: SyncResult) -> None:
    """Diff-apply all three child types at ``new_version`` (delete-absent = full-sync semantics)."""
    active = _active(db, server.id)
    _apply(db, server.id, new_version, result.tools, active["tools"], "name", _tool_fields)
    _apply(db, server.id, new_version, result.resources, active["resources"], "uri", _resource_fields)
    _apply(db, server.id, new_version, result.prompts, active["prompts"], "name", _prompt_fields)


# --- Partial sync (granular mutation + additive cascade) --------------------

_CHILD = {
    "tool": (McpToolRow, "name"),
    "resource": (McpResourceRow, "uri"),
    "prompt": (McpPromptRow, "name"),
}
_SETTERS = {}  # populated after the field setters are defined (see bottom)


def add_tool(db, server, definition):
    return apply_partial(db, server, child="tool", op="add", definition=definition,
                         cascade=CascadeFlags(prompts=True))


def update_tool(db, server, definition):
    return apply_partial(db, server, child="tool", op="update", definition=definition,
                         cascade=CascadeFlags(prompts=True))


def add_prompt(db, server, definition):
    return apply_partial(db, server, child="prompt", op="add", definition=definition,
                         cascade=CascadeFlags())


def update_prompt(db, server, definition):
    return apply_partial(db, server, child="prompt", op="update", definition=definition,
                         cascade=CascadeFlags())


def add_resource(db, server, definition):
    return apply_partial(db, server, child="resource", op="add", definition=definition,
                         cascade=CascadeFlags(tools=True, prompts=True))


def update_resource(db, server, definition):
    """Update a resource. The schema (entity-relationship) resource edits relationships/FKs (cascades);
    an entity resource edits **title + description + kind** (cosmetic, no cascade). ``kind`` may be
    flipped between ``primary_entity`` and ``secondary_entity`` only — never to/from ``schema``."""
    uri = definition.get("uri")
    existing = _active_one(db, McpResourceRow, server.id, "uri", uri) if uri else None
    if existing is None:
        raise ValidationError(f"unknown resource '{uri}'")
    if existing.kind == "schema":
        return _update_schema_resource(db, server, existing, definition)
    safe = {"uri": uri}
    if "title" in definition:
        safe["title"] = definition["title"]
    if "description" in definition:
        safe["description"] = definition["description"]
    if "kind" in definition:
        kind = definition["kind"]
        if kind not in ("primary_entity", "secondary_entity"):
            raise ValidationError("entity kind must be 'primary_entity' or 'secondary_entity'")
        safe["kind"] = kind
    return apply_partial(db, server, child="resource", op="update", definition=safe, cascade=CascadeFlags())


# --- Hard delete (manual; not LLM-driven) + LLM-driven prune cascade --------

def delete_tool(db, server, name):
    """Hard-delete a tool, then regenerate prompts (prune) so orphaned prompts drop out."""
    return _delete_child(db, server, child="tool", key_val=name, cascade=CascadeFlags(prompts=True))


def delete_prompt(db, server, name):
    """Hard-delete a prompt (a leaf — no cascade)."""
    return _delete_child(db, server, child="prompt", key_val=name, cascade=CascadeFlags())


def delete_resource(db, server, uri):
    """Hard-delete an entity resource: drop its backing table, clean the entity-relationship schema,
    then regenerate tools + prompts (prune). The schema resource itself cannot be deleted."""
    new_version = (server.version or 1) + 1
    row = _active_one(db, McpResourceRow, server.id, "uri", uri)
    if row is None:
        raise ValidationError(f"unknown resource '{uri}'")
    if row.kind == "schema":
        raise ValidationError("the entity-relationship (schema) resource cannot be deleted")
    table_name = (row.content or {}).get("table") or row.name
    db.delete(row)              # hard delete the entity resource (manual action)
    db.flush()
    _drop_table(server, table_name)            # remove backing parquet table + catalog entry
    _remove_table_from_schema(db, server, table_name)   # clean relationships referencing it
    tools_changed, dropped = _cascade_tools(db, server, new_version, prune=True)
    prompts_changed = _cascade_prompts(db, server, new_version, prune=True)
    server.version = new_version
    server.last_synced_at = _now()
    server.last_sync_status = "partial" if dropped else "ok"
    log.info("sync.delete_resource", server=server.name, uri=uri, table=table_name, version=new_version)
    return PartialResult("resource", "delete", uri, tools_changed, prompts_changed, server.last_sync_status)


def _delete_child(db: Session, server: DatabaseRow, *, child: str, key_val: str,
                  cascade: CascadeFlags) -> PartialResult:
    """Hard-delete one tool/prompt by key, then run a pruning cascade of dependents (one version bump)."""
    model, key = _CHILD[child]
    row = _active_one(db, model, server.id, key, key_val)
    if row is None:
        raise ValidationError(f"unknown {child} '{key_val}'")
    new_version = (server.version or 1) + 1
    db.delete(row)             # hard delete (manual action — not a reversible LLM suggestion)
    db.flush()
    tools_changed = prompts_changed = False
    status = "ok"
    if cascade.tools:
        tools_changed, dropped = _cascade_tools(db, server, new_version, prune=True)
        if dropped:
            status = "partial"
    if cascade.prompts:
        prompts_changed = _cascade_prompts(db, server, new_version, prune=True)
    server.version = new_version
    server.last_synced_at = _now()
    server.last_sync_status = status
    log.info("sync.delete", server=server.name, child=child, key=key_val, version=new_version)
    return PartialResult(child, "delete", key_val, tools_changed, prompts_changed, status)


def _update_schema_resource(db: Session, server: DatabaseRow, existing, definition: dict) -> PartialResult:
    """Manually edit the entity-relationship schema (relationships/FKs, title/description), then cascade.

    The schema lives on this resource's ``content`` (the source of truth) — there is no entity column.
    """
    new_version = (server.version or 1) + 1
    src = definition.get("content") if isinstance(definition.get("content"), dict) else definition
    content = _schema_content({"relationships": src.get("relationships") or []})
    if "title" in definition:
        existing.title = definition["title"]
    if "description" in definition:
        existing.description = definition["description"]
    existing.content = content
    existing.size = len(json.dumps(content).encode())
    db.flush()
    tools_changed, dropped = _cascade_tools(db, server, new_version, prune=False)
    prompts_changed = _cascade_prompts(db, server, new_version, prune=False)
    server.version = new_version
    server.last_synced_at = _now()
    server.last_sync_status = "partial" if dropped else "ok"
    log.info("sync.update_schema", server=server.name, version=new_version)
    return PartialResult("resource", "update", existing.uri, tools_changed, prompts_changed,
                         server.last_sync_status)


def _drop_table(server: DatabaseRow, table_name: str) -> None:
    """Drop a table from the underlying database via its connector (parquet: file; external: no-op)."""
    try:
        _connector(server).drop_table(table_name)
    except Exception as exc:
        log.warning("sync.drop_table.failed", table=table_name, error=str(exc))


def _remove_table_from_schema(db: Session, server: DatabaseRow, table_name: str) -> None:
    """Drop any relationships/FKs referencing ``table_name`` from the schema resource's content."""
    schema_row = (
        db.query(McpResourceRow)
        .filter(McpResourceRow.database_id == server.id, McpResourceRow.deleted_at.is_(None),
                McpResourceRow.kind == "schema")
        .first()
    )
    if schema_row is None:
        return
    rels = [r for r in (schema_row.content or {}).get("relationships", [])
            if table_name not in (r.get("from_table"), r.get("to_table"))]
    content = {"relationships": rels}
    schema_row.content = content
    schema_row.size = len(json.dumps(content).encode())


def apply_partial(db: Session, server: DatabaseRow, *, child: str, op: str,
                  definition: dict, cascade: CascadeFlags) -> PartialResult:
    """Apply ONE explicit mutation + its additive cascade at one new version, in the caller's txn."""
    new_version = (server.version or 1) + 1
    key_val = _apply_one(db, server, new_version, child, op, definition)
    tools_changed = prompts_changed = False
    status = "ok"
    if cascade.tools:
        tools_changed, dropped = _cascade_tools(db, server, new_version)
        if dropped:
            status = "partial"
    if cascade.prompts:
        prompts_changed = _cascade_prompts(db, server, new_version)
    server.version = new_version
    server.last_synced_at = _now()
    server.last_sync_status = status
    log.info("sync.partial", server=server.name, child=child, op=op, key=key_val, version=new_version,
             status=status)
    return PartialResult(child, op, key_val, tools_changed, prompts_changed, status)


def _apply_one(db: Session, server: DatabaseRow, new_version: int, child: str, op: str,
               definition: dict) -> str:
    """Insert-or-update exactly ONE child row at ``new_version``. Validates before mutating."""
    if child not in _CHILD:
        raise ValidationError(f"unknown capability type: {child!r}")
    model, key = _CHILD[child]
    set_fields = _SETTERS[child]
    key_val = definition.get(key)
    if not key_val:
        raise ValidationError(f"missing '{key}'")
    existing = _active_one(db, model, server.id, key, key_val)
    if op == "add":
        if existing is not None:
            raise ValidationError(f"{child} '{key_val}' already exists; use {child}s/update")
        if child == "resource" and definition.get("kind") == "schema":
            raise ValidationError("the 'schema' resource is managed by sync and cannot be added")
        effective = definition
        if child == "tool":
            _validate_tool_definition(db, server, effective)
        row = model()
        row.database_id = server.id
        row.created_version = new_version
        set_fields(row, effective)
        db.add(row)
    elif op == "update":
        if existing is None:
            raise ValidationError(f"unknown {child} '{key_val}'")
        if child == "resource" and existing.kind == "schema":
            raise ValidationError("the 'schema' resource is managed by sync and cannot be edited")
        # PATCH semantics: keep fields the client didn't supply (don't reset to defaults).
        effective = {**_row_to_def(child, existing), **definition}
        if child == "tool":
            _validate_tool_definition(db, server, effective)
        set_fields(existing, effective)
    else:
        raise ValidationError(f"unknown op: {op!r}")
    db.flush()
    return key_val


def _row_to_def(child: str, row) -> dict:
    """Project a capability row back to its stage-shaped definition (for patch-merge on update)."""
    if child == "tool":
        return {"name": row.name, "title": row.title, "description": row.description,
                "execution": row.execution, "output_schema": row.output_schema,
                "annotations": row.annotations}
    if child == "resource":
        return {"uri": row.uri, "name": row.name, "title": row.title, "description": row.description,
                "mime_type": row.mime_type, "kind": row.kind, "content": row.content, "size": row.size}
    return {"name": row.name, "title": row.title, "description": row.description,
            "arguments": row.arguments, "template": row.template}


def _cascade_tools(db: Session, server: DatabaseRow, new_version: int, prune: bool = False) -> tuple[bool, bool]:
    """Regenerate tools from current active entities + physical tables.

    ``prune=False`` (add/update): additive — insert/update only. ``prune=True`` (delete): also
    soft-delete tools no longer proposed (an LLM-driven regen, so reversible soft-delete).
    """
    active = _active(db, server.id)
    entities = [{"name": r.name, "kind": r.kind} for r in active["resources"]
                if r.kind in ("primary_entity", "secondary_entity")]
    tables = active_entity_tables(db, server.id)  # from resources — cascades never re-inspect the store
    proposed = stages.stage_tools(server.name, entities, tables, _meta(active["tools"], "name"))
    proposed, dropped = _validate_tools(server, _connector(server), [t["table_name"] for t in tables], proposed)
    _apply(db, server.id, new_version, proposed, active["tools"], "name", _tool_fields, delete_absent=prune)
    db.flush()
    return bool(proposed), dropped


def _cascade_prompts(db: Session, server: DatabaseRow, new_version: int, prune: bool = False) -> bool:
    """Regenerate prompts from current active tools (``prune`` soft-deletes orphaned prompts on delete)."""
    active = _active(db, server.id)
    proposed = stages.stage_prompts(server.name, _meta(active["tools"], "name"),
                                    _meta(active["prompts"], "name"))
    _apply(db, server.id, new_version, proposed, active["prompts"], "name", _prompt_fields,
           delete_absent=prune)
    db.flush()
    return bool(proposed)


def _validate_tool_definition(db: Session, server: DatabaseRow, definition: dict) -> None:
    """Reject a non-SELECT / multi-statement / forbidden / undeclared-param tool at write time.

    Validates the canonical ``execution`` object: the ``sql_template`` (with ``$param`` embeddings) and
    the ``parameters`` declaring each embedding. Every ``$param`` must be declared in ``parameters``.
    The compile-check builds views over the database's resource-table tables (no re-inspection).
    """
    execution = normalize_execution(definition)
    sql = (execution.get("sql_template") or "").strip()
    if not sql:
        raise ValidationError("tool execution.sql_template is required")
    try:
        _guard_select(sql)
    except RecoverableQueryError as exc:
        raise ValidationError(f"sql_template rejected: {exc}")
    used = set(_PARAM.findall(sql))
    declared = {p.get("name") for p in (execution.get("parameters") or []) if p.get("name")}
    missing = used - declared
    if missing:
        raise ValidationError(
            f"sql_template uses param(s) not declared in execution.parameters: {', '.join(sorted(missing))}")
    if not used and (server.type or "parquet") == "parquet":
        table_names = [t["table_name"] for t in active_entity_tables(db, server.id)]
        conn = getattr(_connector(server).build_server(table_names), "_duckdb_conn", None)
        try:
            _run_select_params(conn, f"SELECT * FROM ({sql}) AS _v LIMIT 0", None, 0)
        except Exception as exc:
            raise ValidationError(f"sql_template does not compile: {exc}")
        finally:
            if conn is not None:
                conn.close()


# --- Generic diff/merge apply -----------------------------------------------

def _apply(db, database_id, new_version, proposed, active_rows, key, set_fields, delete_absent=True):
    """Insert new / update matched. If ``delete_absent`` (full sync), soft-delete rows not proposed."""
    by_key = {getattr(r, key): r for r in active_rows}
    seen: set[str] = set()
    for item in proposed:
        k = item.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        existing = by_key.get(k)
        if existing is not None:
            set_fields(existing, item)
        else:
            new_row = _new_row_for(set_fields)
            new_row.database_id = database_id
            new_row.created_version = new_version
            set_fields(new_row, item)
            db.add(new_row)
    if delete_absent:
        for k, row in by_key.items():
            if k not in seen:
                row.deleted_at = _now()
                row.deleted_version = new_version


def _new_row_for(set_fields):
    return {_tool_fields: McpToolRow, _resource_fields: McpResourceRow, _prompt_fields: McpPromptRow}[set_fields]()


def _tool_fields(row: McpToolRow, item: dict) -> None:
    row.name = item["name"]
    row.title = item.get("title")
    row.description = item.get("description") or ""
    row.execution_json = json.dumps(normalize_execution(item))
    row.output_schema_json = json.dumps(item["output_schema"]) if item.get("output_schema") else None
    row.annotations_json = json.dumps(item["annotations"]) if item.get("annotations") else None


def _params_from_input_schema(input_schema: dict | None) -> list[dict]:
    """Derive execution ``parameters`` from a legacy/clientside MCP ``inputSchema`` object."""
    props = ((input_schema or {}).get("properties")) or {}
    required = set((input_schema or {}).get("required") or [])
    params: list[dict] = []
    for name, spec in props.items():
        p: dict = {"name": name, "type": (spec or {}).get("type") or "string"}
        if (spec or {}).get("description"):
            p["description"] = spec["description"]
        if name in required:
            p["required"] = True
        params.append(p)
    return params


def normalize_execution(item: dict) -> dict:
    """Coerce a tool definition into the canonical ``{"sql_template", "parameters"}`` execution object.

    Accepts the new ``execution`` object directly, or a legacy top-level ``sql_template`` (+ optional
    ``input_schema`` from which parameter specs are derived) so older callers/tests still work.
    """
    execution = item.get("execution")
    if isinstance(execution, dict) and (execution.get("sql_template") or execution.get("parameters")):
        params = execution.get("parameters")
        if params is None:
            params = _params_from_input_schema(item.get("input_schema"))
        return {"sql_template": execution.get("sql_template") or "", "parameters": params or []}
    return {
        "sql_template": item.get("sql_template") or "",
        "parameters": _params_from_input_schema(item.get("input_schema")),
    }


def _resource_fields(row: McpResourceRow, item: dict) -> None:
    row.uri = item["uri"]
    row.name = item.get("name") or item["uri"]
    row.title = item.get("title")
    row.description = item.get("description")
    row.mime_type = item.get("mime_type")
    row.kind = item.get("kind") or "primary_entity"
    row.content_json = json.dumps(item["content"]) if item.get("content") is not None else None
    row.size = item.get("size")


def _prompt_fields(row: McpPromptRow, item: dict) -> None:
    row.name = item["name"]
    row.title = item.get("title")
    row.description = item.get("description")
    row.arguments_json = json.dumps(item.get("arguments") or [])
    row.template_json = json.dumps(item["template"]) if item.get("template") is not None else None


_SETTERS.update({"tool": _tool_fields, "resource": _resource_fields, "prompt": _prompt_fields})


# --- Helpers ----------------------------------------------------------------

def _active(db: Session, database_id: str) -> dict[str, list]:
    """Load the active (non-soft-deleted) child rows for a server."""
    def q(model):
        return (
            db.query(model)
            .filter(model.database_id == database_id, model.deleted_at.is_(None))
            .order_by(model.created_at, model.id)
            .all()
        )
    return {"tools": q(McpToolRow), "resources": q(McpResourceRow), "prompts": q(McpPromptRow)}


def active_entity_tables(db: Session, database_id: str) -> list[dict]:
    """The database's tables **from the resources table** (entity resources), in ``discover_tables`` shape.

    This is the materialized source of truth used everywhere OUTSIDE sync (pool build, query execution,
    write-time validation, the EER view) — so the serving path never re-inspects the underlying store.
    """
    rows = (
        db.query(McpResourceRow)
        .filter(McpResourceRow.database_id == database_id, McpResourceRow.deleted_at.is_(None),
                McpResourceRow.kind != "schema")
        .order_by(McpResourceRow.created_at, McpResourceRow.id)
        .all()
    )
    tables: list[dict] = []
    for r in rows:
        content = r.content or {}
        cols = content.get("columns") or []
        tables.append({
            "table_name": content.get("table") or r.name,
            "column_names": [c.get("name") for c in cols],
            "schema": cols,
            "row_count": content.get("row_count"),
        })
    return tables


def _active_schema_content(resources: list) -> dict:
    """The entity-relationship schema content from the active ``kind='schema'`` resource (or ``{}``)."""
    for r in resources:
        if r.kind == "schema":
            return r.content or {}
    return {}


def _active_one(db, model, database_id, key, key_val):
    return (
        db.query(model)
        .filter(model.database_id == database_id, model.deleted_at.is_(None), getattr(model, key) == key_val)
        .first()
    )


def _meta(rows: list, *fields: str) -> list[dict]:
    """Project active rows to plain dicts for the stage prompts (existing-capability hints)."""
    return [{f: getattr(r, f, None) for f in fields} for r in rows]


def _schema_resource(name: str, schema: dict) -> dict:
    """The entity-relationship resource: relationships + foreign keys ONLY (no per-table columns).

    Together with the per-entity resources (which carry each table's columns) this is the full schema
    source of truth. This resource is tied to the server's existence (never added/deleted, only updated).
    """
    content = _schema_content(schema)
    return {
        "uri": f"dataset://{name}/schema",
        "name": "schema",
        "title": "Entity relationships",
        "description": "Foreign-key and entity relationships across the dataset's tables.",
        "kind": "schema",
        "mime_type": "application/json",
        "content": content,
        "size": len(json.dumps(content).encode()),  # size of the relationship content (bytes)
    }


def _schema_content(schema: dict) -> dict:
    """Project to the **canonical schema-resource shape** — a single relationship (FK-edge) list.

    ``{"relationships": [{"from_table","from_column","to_table","to_column"}]}`` — the one format the
    EER diagram reads and every connector + the LLM must produce, regardless of database type.
    """
    rels = (schema or {}).get("relationships") or []
    norm = [
        {
            "from_table": r.get("from_table") or r.get("from"),
            "from_column": r.get("from_column") or r.get("on"),
            "to_table": r.get("to_table") or r.get("to"),
            "to_column": r.get("to_column") or r.get("on"),
        }
        for r in rels
    ]
    return {"relationships": [r for r in norm if r["from_table"] and r["to_table"]]}


def _entity_resource(name: str, entity: dict, tables_by_name: dict) -> dict:
    """A per-entity resource carrying its backing table's columns (the per-table schema source)."""
    table = entity.get("name")
    t = tables_by_name.get(table) or {}
    columns = t.get("schema") or [{"name": c} for c in (t.get("column_names") or [])]
    return {
        "uri": entity.get("uri") or f"entity://{name}/{table}",
        "name": table or "entity",
        "title": entity.get("title"),
        "description": entity.get("description"),
        "kind": entity.get("kind") or "primary_entity",
        "mime_type": entity.get("mime_type") or "application/json",
        "content": {"table": table, "columns": columns, "row_count": t.get("row_count")},
        "size": _table_size(t.get("parquet_path")),  # size of the backing table file (bytes)
    }


def _table_size(parquet_path: str | None) -> int | None:
    """Return the on-disk size (bytes) of a table's Parquet file, or ``None`` if unavailable."""
    if not parquet_path:
        return None
    try:
        return Path(parquet_path).stat().st_size
    except Exception:
        return None


def _validate_tools(server: DatabaseRow, connector, table_names: list[str], tools: list[dict]) -> tuple[list[dict], bool]:
    """Drop tools whose zero-param SQL doesn't compile against the database (parquet only).

    Compile-checks against a connection the connector builds over ``table_names`` (no re-inspection).
    """
    if (server.type or "parquet") != "parquet":
        return tools, False  # external (BETA): trust the generated SQL
    conn = getattr(connector.build_server(table_names), "_duckdb_conn", None)
    try:
        kept: list[dict] = []
        dropped = False
        for tool in tools:
            execution = normalize_execution(tool)
            sql = execution.get("sql_template") or ""
            if execution.get("parameters"):
                kept.append(tool)  # can't safely compile-check parameterized SQL — trust it
                continue
            try:
                _run_select_params(conn, f"SELECT * FROM ({sql}) AS _v LIMIT 0", None, 0)
                kept.append(tool)
            except Exception as exc:
                dropped = True
                log.warning("sync.tool_invalid", name=tool.get("name"), error=str(exc))
        return kept, dropped
    finally:
        if conn is not None:
            conn.close()
