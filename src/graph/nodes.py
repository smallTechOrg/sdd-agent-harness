"""Graph nodes for the NL -> SQL analysis pipeline.

Pipeline: ``plan_sql -> execute_sql -> finalize`` with a conditional
``handle_error`` branch (see spec/agent.md). The only LLM call is in
``plan_sql``; ``execute_sql`` is pure local DuckDB.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from graph.state import AgentState
from llm.client import LLMClient
from observability.events import get_logger
from analytics import duckdb_engine
from analytics.sql_guard import is_read_only_select
from analytics.seed import SALES_TABLE

log = get_logger("graph.nodes")

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "plan_sql.md"

_VALID_CHART_TYPES = {"bar", "line", "pie", "scatter", "table"}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _active_table(state: AgentState) -> str:
    """Resolve the active dataset table. Phase 1: always the seeded sales table."""
    return state.get("dataset_id") or SALES_TABLE


def _extract_json(text: str) -> dict:
    """Parse a JSON object from an LLM reply, tolerant of code fences/prose."""
    if not text or not text.strip():
        raise ValueError("Empty LLM reply.")
    cleaned = text.strip()

    # Strip ```json ... ``` or ``` ... ``` fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the first {...} object in the text.
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("LLM reply was not valid JSON.")


def _normalise_chart_spec(spec, columns: list[str] | None = None) -> dict:
    """Validate/repair the chart_spec; fall back to a plain table."""
    fallback = {"chart_type": "table", "x": None, "y": []}
    if not isinstance(spec, dict):
        return fallback

    chart_type = str(spec.get("chart_type", "")).lower()
    if chart_type not in _VALID_CHART_TYPES:
        chart_type = "table"

    x = spec.get("x")
    y = spec.get("y")
    if isinstance(y, str):
        y = [y]
    if not isinstance(y, list):
        y = []

    return {"chart_type": chart_type, "x": x, "y": y}


class _JSONEncoder(json.JSONEncoder):
    """Encode DuckDB cell types (date/datetime/Decimal) that aren't JSON-native."""

    def default(self, o):  # noqa: D401
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _serialise_payload(payload: dict) -> str:
    return json.dumps(payload, cls=_JSONEncoder)


def plan_sql(state: AgentState) -> AgentState:
    """Introspect the active dataset, ask Gemini for SQL + chart_spec, guard it."""
    run_id = state.get("run_id")
    table = _active_table(state)
    try:
        info = duckdb_engine.introspect(table)
        schema = info["schema"]
        sample_rows = info["sample_rows"]
        sample_columns = info.get("sample_columns", [c["column"] for c in schema])

        # Privacy-bounded context: schema + <= N sample rows ONLY.
        context = {
            "table": table,
            "schema": schema,
            "sample_columns": sample_columns,
            "sample_rows": sample_rows,
        }
        prompt = (
            f"Question: {state['input_text']}\n\n"
            f"Table and schema (JSON):\n{_serialise_payload(context)}"
        )

        reply = LLMClient().call_model(prompt, system=_load_prompt())
        parsed = _extract_json(reply)

        sql = str(parsed.get("sql", "")).strip()
        if not sql:
            raise ValueError("The model did not return any SQL.")
        if not is_read_only_select(sql):
            raise ValueError("The model did not return a valid read-only SELECT.")

        chart_spec = _normalise_chart_spec(parsed.get("chart_spec"))
        log.info(
            "plan_sql",
            run_id=run_id,
            table=table,
            chart_type=chart_spec["chart_type"],
        )
        return {
            **state,
            "schema": schema,
            "sample_rows": sample_rows,
            "sql": sql,
            "chart_spec": chart_spec,
            "error": None,
        }
    except Exception as exc:
        log.error("plan_sql_failed", run_id=run_id, table=table, error=str(exc))
        return {**state, "error": str(exc)}


def execute_sql(state: AgentState) -> AgentState:
    """Re-assert the guard, run the SELECT, write bounded columns/rows."""
    run_id = state.get("run_id")
    sql = state.get("sql", "")
    try:
        if not is_read_only_select(sql):
            raise ValueError("Refused to execute a non-read-only statement.")
        result = duckdb_engine.run_select(sql)
        log.info("execute_sql", run_id=run_id, row_count=len(result["rows"]))
        return {
            **state,
            "columns": result["columns"],
            "rows": result["rows"],
            "error": None,
        }
    except Exception as exc:
        log.error("execute_sql_failed", run_id=run_id, error=str(exc))
        return {**state, "error": str(exc)}


def finalize(state: AgentState) -> AgentState:
    """Serialize the success payload into output_text."""
    payload = {
        "sql": state.get("sql"),
        "columns": state.get("columns", []),
        "rows": state.get("rows", []),
        "chart_spec": state.get("chart_spec") or {"chart_type": "table", "x": None, "y": []},
        "error": None,
    }
    return {**state, "status": "completed", "output_text": _serialise_payload(payload)}


def handle_error(state: AgentState) -> AgentState:
    """Serialize a consistent failure payload so the UI always gets the same shape."""
    error = state.get("error") or "The run failed."
    log.error("handle_error", run_id=state.get("run_id"), error=error)
    payload = {
        "sql": state.get("sql"),
        "columns": [],
        "rows": [],
        "chart_spec": None,
        "error": error,
    }
    return {**state, "status": "failed", "output_text": _serialise_payload(payload)}
