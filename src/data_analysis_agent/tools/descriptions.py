from __future__ import annotations

import json
from typing import NamedTuple

import pandas as pd
import structlog

log = structlog.get_logger()

# Prompt tag the stub provider branches on — must not change without updating stub.py.
_DESCRIBE_TAG = "<node:describe_tool>"

_DESCRIBE_INTRO = [
    _DESCRIBE_TAG,
    "You are a data catalog assistant. Analyze the dataset below and write",
    "concise, accurate metadata descriptions for the tool registry.",
    "",
]

_DESCRIBE_INSTRUCTIONS = [
    "Write exactly two short descriptions (1-2 sentences each):",
    "  tool_description      — what the dataset contains and what questions it can answer.",
    "  capability_description — what the run_query SQL capability does on this table.",
    "",
    "Respond with ONLY a JSON object, no prose, no markdown fences:",
    '{"tool_description": "...", "capability_description": "..."}',
]


class ToolDescriptions(NamedTuple):
    """A generated tool description and its capability description."""

    tool: str
    capability: str


def generate_tool_descriptions(
    filename: str,
    table_name: str,
    schema: list[dict],
    row_count: int,
    parquet_path: str,
) -> ToolDescriptions:
    """Ask the LLM to describe a dataset's tool and run_query capability.

    Samples the Parquet file, prompts the LLM, and parses the JSON reply. Any
    failure (stub mode, network error, malformed JSON, missing file) falls back
    silently to deterministic templates so uploads never fail.
    """
    fallback = _fallback_descriptions(filename, table_name)
    try:
        prompt = _build_describe_prompt(filename, table_name, schema, row_count, parquet_path)
        from data_analysis_agent.llm.client import get_llm_client
        result = get_llm_client().complete(prompt)
        descriptions = _parse_descriptions(result.text or "", fallback)
        log.info("descriptions.generated", filename=filename)
        return descriptions
    except Exception as exc:
        log.warning("descriptions.fallback", filename=filename, error=str(exc))
        return fallback


def _fallback_descriptions(filename: str, table_name: str) -> ToolDescriptions:
    """Return deterministic descriptions used when the LLM call cannot be trusted."""
    return ToolDescriptions(
        tool=f"Execute SQL SELECT queries against '{filename}' (table: {table_name}).",
        capability=(
            f"Execute a SQL SELECT statement against '{filename}'. "
            f"Table name is '{table_name}'."
        ),
    )


def _build_describe_prompt(
    filename: str,
    table_name: str,
    schema: list[dict],
    row_count: int,
    parquet_path: str,
) -> str:
    """Build the catalog-assistant prompt that asks for JSON descriptions."""
    schema_lines = "\n".join(
        f"  {c['name']} ({c['dtype']}{'?' if c['nullable'] else ''})" for c in schema
    )
    sample_csv = pd.read_parquet(parquet_path).head(5).to_csv(index=False)
    body = [
        f"File name:      {filename}",
        f"SQL table name: {table_name}",
        f"Row count:      {row_count}",
        "",
        "Column schema  (name, dtype, ? = nullable):",
        schema_lines,
        "",
        "Sample data (first 5 rows):",
        sample_csv,
        "",
    ]
    return "\n".join([*_DESCRIBE_INTRO, *body, *_DESCRIBE_INSTRUCTIONS])


def _parse_descriptions(raw: str, fallback: ToolDescriptions) -> ToolDescriptions:
    """Parse the model's JSON reply, tolerating markdown fences; fall back per field."""
    parsed = json.loads(_strip_markdown_fences(raw.strip()))
    return ToolDescriptions(
        tool=parsed.get("tool_description") or fallback.tool,
        capability=parsed.get("capability_description") or fallback.capability,
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove a leading ``` fence (and optional language tag) some models emit."""
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[1:end]).strip()
