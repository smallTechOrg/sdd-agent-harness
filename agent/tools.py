"""Tools — plain typed in-process @tool (harness/patterns/tools-and-mcp.md). No MCP: nothing is external.

The active dataset for a run is held in a ContextVar set by agent/runner.py before the graph is invoked, so
the model never has to pass a dataset UUID — it just asks for the schema or runs a query and the tool
resolves which dataset. Every tool fails SOFT (returns an error string, never raises) so the model can
recover; the loop persists tool spans (harness/patterns/observability-and-evals.md).
"""
import contextvars
import json

from langchain_core.tools import tool

from . import duck
from .config import get_settings
from .guardrails import validate_read_only

# Set by run_agent() before graph.ainvoke(); read by get_schema / run_sql within the same async task.
current_dataset: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_dataset", default=None)


def _dataset_id() -> str | None:
    return current_dataset.get()


@tool
def get_schema(table: str = "") -> str:
    """List the dataset's tables with their columns, types, and a few sample rows.

    Call this FIRST, before writing SQL, so you use exact table and column names. Pass an empty string to
    see every table (recommended), or a single table name to focus on one.
    """
    ds = _dataset_id()
    if not ds:
        return "No dataset is selected for this run."
    schema = duck.dataset_schema(ds)
    tables = schema["tables"]
    if table:
        tables = [t for t in tables if t["table"] == table]
    if not tables:
        return "This dataset has no tables yet — upload a CSV/JSON file first."
    out = []
    for t in tables:
        cols = ", ".join(f'{c["name"]} ({c["type"]})' for c in t["columns"])
        out.append(f'TABLE "{t["table"]}" ({len(t["columns"])} columns)\n  columns: {cols}')
        if t["sample_rows"]:
            names = [c["name"] for c in t["columns"]]
            sample = "; ".join(str(dict(zip(names, r))) for r in t["sample_rows"])
            out.append(f"  sample rows: {sample}")
    return "\n".join(out)


@tool
def run_sql(sql: str) -> str:
    """Run ONE read-only SQL SELECT against the current dataset and return the result rows.

    Read-only only (SELECT / WITH). Any INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/COPY/ATTACH/PRAGMA is
    refused. Use exact table/column names from get_schema (quote identifiers containing spaces). Aggregate
    for a single number; add LIMIT when returning rows. Results are capped to a configured row limit.
    """
    ok, reason = validate_read_only(sql)
    if not ok:
        return f"REFUSED (read-only queries only): {reason}"
    ds = _dataset_id()
    if not ds:
        return "No dataset is selected for this run."
    settings = get_settings()
    result = duck.run_query(ds, sql, settings.max_query_rows)
    if "error" in result:
        return f"SQL error: {result['error']}"
    payload = {"columns": result["columns"], "rows": result["rows"], "row_count": result["row_count"]}
    if result["truncated"]:
        payload["note"] = f"results truncated to {settings.max_query_rows} rows"
    return json.dumps(payload, ensure_ascii=False, default=str)


@tool
def write_todos(todos: list[str]) -> str:
    """Record a short ordered plan (the Deep-Agent planning scratchpad). Call before multi-step analysis."""
    return "Plan recorded:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(todos))


@tool
def finish(answer: str) -> str:
    """Return the final answer to the user and end the run. Call exactly once when done.

    Lead with the direct, numeric answer; reference any chart you created; add one short grounded insight.
    """
    return answer


TOOLS = [get_schema, run_sql, write_todos, finish]
TOOL_MAP = {t.name: t for t in TOOLS}
FINISH = "finish"
