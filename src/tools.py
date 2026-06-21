"""Tools — plain typed in-process @tool (harness/patterns/tools-and-mcp.md). No MCP: nothing is external.

Five tools matching spec/capabilities/*.md:
  list_datasets        — list ingested datasets (names + row counts)
  get_dataset_schema   — columns, types, sample rows for one dataset
  execute_sql          — read-only SELECT against a dataset (SELECT-only; also checked by guardrails.py)
  generate_chart_spec  — produce a Plotly JSON spec from query results
  finish               — emit the final answer (+ optional chart_spec) and end the run

All tools fail SOFT (return an error string, never raise) so the model can recover; the loop persists
tool spans (harness/patterns/observability-and-evals.md).
"""
import json

from langchain_core.tools import tool

from . import duck
from .config import get_settings
from .guardrails import validate_read_only


@tool
def list_datasets() -> str:
    """List all datasets that have been uploaded in this session, with their table names and row counts.

    Call this first if you don't know what data is available.
    """
    schema = duck.list_all_datasets()
    if not schema:
        return "No datasets have been uploaded yet. Ask the user to upload a CSV or JSON file."
    lines = []
    for ds in schema:
        tables = ", ".join(f'{t["table"]} ({t["n_rows"]} rows)' for t in ds["tables"])
        lines.append(f'Dataset "{ds["name"]}" (id={ds["id"]}): {tables or "no tables yet"}')
    return "\n".join(lines)


@tool
def get_dataset_schema(dataset_id: str, table: str = "") -> str:
    """Return the schema (column names, types, sample rows) for a dataset.

    Pass dataset_id from list_datasets. Pass table to focus on one table; leave empty for all tables.
    Call this BEFORE writing SQL to confirm exact column and table names.
    """
    schema = duck.dataset_schema(dataset_id)
    tables = schema["tables"]
    if table:
        tables = [t for t in tables if t["table"] == table]
    if not tables:
        return f"No tables found for dataset {dataset_id!r}. Upload a file first."
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
def execute_sql(dataset_id: str, sql: str) -> str:
    """Run ONE read-only SQL SELECT against a dataset and return the result rows as JSON.

    Read-only only (SELECT / WITH). INSERT/UPDATE/DELETE/DROP/ALTER/CREATE are refused.
    Use exact table/column names from get_dataset_schema. Aggregate for a single number;
    add LIMIT when returning rows. Results capped at the configured row limit.
    """
    ok, reason = validate_read_only(sql)
    if not ok:
        return f"REFUSED (read-only queries only): {reason}"
    settings = get_settings()
    result = duck.run_query(dataset_id, sql, settings.max_query_rows)
    if "error" in result:
        return f"SQL error: {result['error']}"
    payload = {"columns": result["columns"], "rows": result["rows"], "row_count": result["row_count"]}
    if result["truncated"]:
        payload["note"] = f"results truncated to {settings.max_query_rows} rows"
    return json.dumps(payload, ensure_ascii=False, default=str)


@tool
def generate_chart_spec(
    query_results: str,
    chart_type: str,
    x_col: str,
    y_col: str,
    title: str = "",
) -> str:
    """Generate a Plotly JSON chart spec from SQL query results.

    Call this after execute_sql when the user's question is naturally answered with a chart.
    query_results: the JSON string returned by execute_sql.
    chart_type: one of bar, line, scatter, pie, histogram.
    x_col: the column name for the x-axis (or labels for pie).
    y_col: the column name for the y-axis (or values for pie).
    title: optional chart title.

    Returns a JSON string with {"data": [...], "layout": {...}} for react-plotly.js.
    Returns a prose message instead if the data is degenerate (0 or 1 row).
    """
    try:
        payload = json.loads(query_results)
    except (json.JSONDecodeError, TypeError):
        return "Could not parse query results for chart generation."

    rows = payload.get("rows", [])
    columns = payload.get("columns", [])
    if len(rows) < 2:
        return f"Not enough data to chart ({len(rows)} row(s)). Provide the answer in prose instead."

    try:
        x_idx = columns.index(x_col)
        y_idx = columns.index(y_col)
    except ValueError:
        avail = ", ".join(columns)
        return f"Column not found. Available columns: {avail}"

    x_vals = [r[x_idx] for r in rows]
    y_vals = [r[y_idx] for r in rows]

    ct = chart_type.lower()
    if ct == "pie":
        trace = {"type": "pie", "labels": x_vals, "values": y_vals}
    elif ct == "histogram":
        trace = {"type": "histogram", "x": x_vals, "name": x_col}
    elif ct == "line":
        trace = {"type": "scatter", "mode": "lines+markers", "x": x_vals, "y": y_vals,
                 "name": y_col}
    elif ct == "scatter":
        trace = {"type": "scatter", "mode": "markers", "x": x_vals, "y": y_vals, "name": y_col}
    else:  # bar (default)
        trace = {"type": "bar", "x": x_vals, "y": y_vals, "name": y_col}

    layout = {
        "title": title or f"{y_col} by {x_col}",
        "xaxis": {"title": x_col},
        "yaxis": {"title": y_col},
        "margin": {"t": 40, "b": 60, "l": 60, "r": 20},
    }
    spec = {"data": [trace], "layout": layout}
    return json.dumps(spec, ensure_ascii=False, default=str)


@tool
def write_todos(todos: list[str]) -> str:
    """Record a short ordered plan (the Deep-Agent planning scratchpad). Call before multi-step analysis."""
    return "Plan recorded:\n" + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(todos))


@tool
def finish(answer: str, chart_spec: str = "") -> str:
    """Return the final answer to the user and end the run. Call exactly once when done.

    answer: the prose answer — lead with the direct result, cite the SQL if relevant.
    chart_spec: optional — the JSON string from generate_chart_spec. Omit if no chart was generated.
    """
    return answer


TOOLS = [list_datasets, get_dataset_schema, execute_sql, generate_chart_spec, write_todos, finish]
TOOL_MAP = {t.name: t for t in TOOLS}
FINISH = "finish"
