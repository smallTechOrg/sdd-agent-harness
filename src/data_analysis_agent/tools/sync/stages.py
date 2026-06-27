"""The five LLM sync stages: title → schema → entities → tools → prompts.

Each stage builds a prompt (with first-5-row samples + the existing capabilities, for incremental
edits), calls the LLM, and parses JSON — falling back to a deterministic template on any failure so
sync never hard-fails. Each stage injects a distinct ``<node:sync_*>`` tag so the offline stub
branches deterministically (see ``llm/providers/stub.py``).
"""
from __future__ import annotations

import json

import pandas as pd
import structlog

log = structlog.get_logger()

TAG_TITLE = "<node:sync_title>"
TAG_SCHEMA = "<node:sync_schema>"
TAG_ENTITIES = "<node:sync_entities>"
TAG_TOOLS = "<node:sync_tools>"
TAG_PROMPTS = "<node:sync_prompts>"


def _llm(prompt: str) -> str:
    from data_analysis_agent.llm.client import get_llm_client
    return get_llm_client().complete(prompt).text or ""


def _sample(parquet_path: str | None) -> str:
    """Return a small CSV sample (first 5 rows) of a Parquet file, or '' on any failure."""
    if not parquet_path:
        return ""
    try:
        return pd.read_parquet(parquet_path).head(5).to_csv(index=False)
    except Exception:
        return ""


def _strip_fences(text: str) -> str:
    """Remove a leading ``` fence (and optional language tag) some models emit."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[1:end]).strip()


def _parse(raw: str) -> dict:
    return json.loads(_strip_fences(raw))


def _table_block(tables: list[dict]) -> list[str]:
    """Render each table's columns + a sample, for a stage prompt."""
    lines: list[str] = []
    for t in tables:
        schema = t.get("schema") or []
        cols = ", ".join(
            f"{c['name']} ({c['dtype']}{'?' if c.get('nullable') else ''})" for c in schema
        ) or ", ".join(t.get("column_names") or []) or "(unknown)"
        lines.append(f"Table: {t['table_name']}  columns: {cols}")
        sample = _sample(t.get("parquet_path"))
        if sample:
            lines.append("  sample (first rows):")
            lines.append(sample)
    return lines


# --- Stage a: title + description -------------------------------------------

def stage_title(name: str, tables: list[dict], existing: dict) -> dict:
    """Return ``{"title", "description"}`` for the server."""
    fallback = {
        "title": existing.get("title") or name,
        "description": existing.get("description")
        or f"MCP server for dataset '{name}' ({len(tables)} table(s)).",
    }
    table_names = ", ".join(t["table_name"] for t in tables) or "(none)"
    prompt = "\n".join([
        TAG_TITLE,
        "You write metadata for an MCP server backed by a tabular dataset.",
        f"Dataset name: {name}",
        f"Tables: {table_names}",
        *_table_block(tables),
        f"Existing title: {existing.get('title') or '(none)'}",
        f"Existing description: {existing.get('description') or '(none)'}",
        'Respond with ONLY JSON: {"title": "...", "description": "..."}',
    ])
    try:
        parsed = _parse(_llm(prompt))
        return {
            "title": parsed.get("title") or fallback["title"],
            "description": parsed.get("description") or fallback["description"],
        }
    except Exception as exc:
        log.warning("sync.stage_title.fallback", error=str(exc))
        return fallback


# --- Stage b: dataset JSONSchema --------------------------------------------

def stage_schema(name: str, tables: list[dict], existing_schema: dict) -> dict:
    """Return the entity-relationship schema in the **canonical** shape — a single FK-edge list:

    ``{"relationships": [{"from_table","from_column","to_table","to_column"}]}``. Relationships ONLY —
    per-table columns live on the individual entity resources, not here. This is the one format the EER
    diagram reads; the LLM must emit exactly this (used only when the connector can't supply FKs).
    """
    fallback = {"relationships": (existing_schema or {}).get("relationships") or []}
    prompt = "\n".join([
        TAG_SCHEMA,
        "Infer the FOREIGN-KEY relationships between the dataset's tables (which column references which).",
        "Do NOT list table columns — only how the tables relate.",
        f"Dataset name: {name}",
        *_table_block(tables),
        f"Existing relationships: {json.dumps(existing_schema) if existing_schema else '(none)'}",
        'Respond with ONLY JSON: {"relationships": [{"from_table": "<table>", "from_column": "<col>", '
        '"to_table": "<table>", "to_column": "<col>"}]}',
    ])
    try:
        return {"relationships": _parse(_llm(prompt)).get("relationships") or []}
    except Exception as exc:
        log.warning("sync.stage_schema.fallback", error=str(exc))
        return fallback


# --- Stage c: entities → resources ------------------------------------------

def stage_entities(name: str, tables: list[dict], existing_resources: list[dict]) -> list[dict]:
    """Return entity resources ``[{name, title, description, kind, uri, mime_type}]`` (one per table)."""
    table_names = [t["table_name"] for t in tables]
    fallback = [
        {
            "name": t,
            "title": t.replace("_", " ").title(),
            "description": f"The '{t}' entity.",
            "kind": "primary_entity",
            "uri": f"entity://{name}/{t}",
            "mime_type": "application/json",
        }
        for t in table_names
    ]
    existing_names = ", ".join(r.get("name", "") for r in existing_resources) or "(none)"
    prompt = "\n".join([
        TAG_ENTITIES,
        "List the primary and secondary entities (one per physical table) backing this dataset.",
        f"Dataset name: {name}",
        f"Schema tables: {', '.join(table_names) or '(none)'}",
        f"Existing resources: {existing_names}",
        'Respond with ONLY JSON: {"entities": [{"name","title","description","kind","uri","mime_type"}]}',
        'name MUST be a physical table name; kind is "primary_entity" or "secondary_entity"; '
        'uri like "entity://<dataset>/<entity>".',
    ])
    try:
        parsed = _parse(_llm(prompt))
        entities = parsed.get("entities")
        return entities if isinstance(entities, list) and entities else fallback
    except Exception as exc:
        log.warning("sync.stage_entities.fallback", error=str(exc))
        return fallback


# --- Stage d: GET-API tools -------------------------------------------------

def stage_tools(name: str, entities: list[dict], tables: list[dict], existing_tools: list[dict]) -> list[dict]:
    """Return GET-API tools ``[{name, title, description, input_schema, sql_template, output_schema?}]``."""
    table_names = [t["table_name"] for t in tables]
    fallback = [
        {
            "name": f"list_{t}",
            "title": f"List {t}",
            "description": f"Return rows from the '{t}' table.",
            "execution": {"sql_template": f"SELECT * FROM {t} LIMIT 100", "parameters": []},
        }
        for t in table_names
    ]
    entity_lines = [f"Entity: {e.get('name')}" for e in entities]
    existing_names = ", ".join(t.get("name", "") for t in existing_tools) or "(none)"
    prompt = "\n".join([
        TAG_TOOLS,
        "Propose GET-API tools — each a read-only SELECT — over these entities.",
        f"Dataset name: {name}",
        *entity_lines,
        f"Tables available: {', '.join(table_names) or '(none)'}",
        f"Existing tools: {existing_names}",
        'Respond with ONLY JSON: {"tools": [{"name","title","description","output_schema",'
        '"execution": {"sql_template": "SELECT ... WHERE col > $param", '
        '"parameters": [{"name": "param", "type": "integer", "description": "..."}]}}]}',
        "execution.sql_template is a single read-only SELECT; every $param embedded in it MUST be "
        "declared in execution.parameters with its type.",
    ])
    try:
        parsed = _parse(_llm(prompt))
        tools = parsed.get("tools")
        return tools if isinstance(tools, list) and tools else fallback
    except Exception as exc:
        log.warning("sync.stage_tools.fallback", error=str(exc))
        return fallback


# --- Stage e: prompt templates ----------------------------------------------

def stage_prompts(name: str, tools: list[dict], existing_prompts: list[dict]) -> list[dict]:
    """Return prompt templates ``[{name, title, description, arguments, template}]``."""
    fallback = [
        {
            "name": f"explore_{t.get('name')}",
            "title": f"Explore via {t.get('name')}",
            "description": f"Guidance for using the '{t.get('name')}' tool.",
            "arguments": [],
            "template": [
                {"role": "user", "content": f"Use the '{t.get('name')}' tool to answer questions about {name}."}
            ],
        }
        for t in tools
    ]
    tool_lines = [f"Tool: {t.get('name')}" for t in tools]
    existing_names = ", ".join(p.get("name", "") for p in existing_prompts) or "(none)"
    prompt = "\n".join([
        TAG_PROMPTS,
        "Propose prompt templates that help a user drive these tools.",
        f"Dataset name: {name}",
        *tool_lines,
        f"Existing prompts: {existing_names}",
        'Respond with ONLY JSON: {"prompts": [{"name","title","description","arguments","template"}]}',
    ])
    try:
        parsed = _parse(_llm(prompt))
        prompts = parsed.get("prompts")
        return prompts if isinstance(prompts, list) and prompts else fallback
    except Exception as exc:
        log.warning("sync.stage_prompts.fallback", error=str(exc))
        return fallback
