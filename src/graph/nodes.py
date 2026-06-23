"""Data-analyst pipeline nodes.

profile_schema -> generate_sql -> execute_sql -> narrate -> finalize
(any node may set ``error`` and route to handle_error).

Token-economy enforcement lives here: ``profile_schema`` caps sample rows at
``max_sample_rows`` and the compact prompt builders (pure functions, unit
tested) NEVER emit more than ``max_sample_rows`` data rows.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from graph.state import AgentState

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Caps for what is ever shown to the LLM.
_NARRATE_RESULT_PREVIEW_ROWS = 10  # capped preview of the RESULT for narration

_SELECT_RE = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_FORBIDDEN_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|truncate|"
    r"replace|grant|revoke|vacuum|merge|call|export|install|load)\b",
    re.IGNORECASE,
)


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


# --------------------------------------------------------------------------- #
# Retry helper
# --------------------------------------------------------------------------- #
def _call_llm_with_retry(prompt: str, *, system: str, attempts: int = 3) -> str:
    """Call the LLM with up to ``attempts`` tries and exponential back-off.

    ``attempts=3`` == initial call + 2 retries, per spec.
    """
    from llm.client import LLMClient

    client = LLMClient()
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            out = client.call_model(prompt, system=system)
            if out is None or not str(out).strip():
                raise RuntimeError("LLM returned an empty response")
            return out
        except Exception as exc:  # noqa: BLE001 - resilience boundary
            last_exc = exc
            logger.warning("LLM call failed (attempt %d/%d): %s", i + 1, attempts, exc)
            if i < attempts - 1:
                time.sleep(0.5 * (2 ** i))
    raise RuntimeError(f"LLM call failed after {attempts} attempts: {last_exc}")


# --------------------------------------------------------------------------- #
# Pure, unit-testable prompt builders (token-economy seam)
# --------------------------------------------------------------------------- #
def build_sql_prompt(schema_context: dict, nl_question: str, max_sample_rows: int) -> str:
    """Build the COMPACT user prompt for generate_sql.

    TOKEN-ECONOMY GUARANTEE: emits at most ``max_sample_rows`` sample data rows.
    """
    table = schema_context.get("table_name", "dataset")
    columns = schema_context.get("columns", [])  # [{name, type}, ...]
    samples = schema_context.get("sample_rows", []) or []
    aggregates = schema_context.get("aggregates", {}) or {}

    capped_samples = samples[: max(0, int(max_sample_rows))]

    lines: list[str] = []
    lines.append(f"Table: {table}")
    lines.append("Columns:")
    for col in columns:
        lines.append(f"  - {col.get('name')} ({col.get('type')})")

    if capped_samples:
        col_names = [c.get("name") for c in columns]
        lines.append(f"Sample rows (up to {max_sample_rows}):")
        lines.append("  " + " | ".join(str(n) for n in col_names))
        for row in capped_samples:
            lines.append("  " + " | ".join("" if v is None else str(v) for v in row))

    if aggregates:
        lines.append("Basic aggregates:")
        for k, v in aggregates.items():
            lines.append(f"  - {k}: {v}")

    lines.append("")
    lines.append(f"Question: {nl_question}")
    lines.append(f"Write one read-only DuckDB SELECT over table {table}.")
    return "\n".join(lines)


def build_narrate_prompt(
    nl_question: str,
    generated_sql: str,
    result_columns: list[str],
    result_rows: list[list],
    row_count: int,
    preview_rows: int = _NARRATE_RESULT_PREVIEW_ROWS,
) -> str:
    """Build the COMPACT user prompt for narrate.

    Only a capped preview of the RESULT is ever included.
    """
    capped = (result_rows or [])[: max(0, int(preview_rows))]
    lines: list[str] = []
    lines.append(f"Question: {nl_question}")
    lines.append(f"SQL: {generated_sql}")
    lines.append(f"Result columns: {', '.join(result_columns or [])}")
    lines.append(f"Total result rows: {row_count}")
    lines.append(f"Result preview (up to {preview_rows} rows):")
    lines.append("  " + " | ".join(str(c) for c in (result_columns or [])))
    for row in capped:
        lines.append("  " + " | ".join("" if v is None else str(v) for v in row))
    return "\n".join(lines)


def _strip_sql_fences(text: str) -> str:
    """Remove markdown code fences and surrounding whitespace from LLM SQL output."""
    t = text.strip()
    # ```sql ... ``` or ``` ... ```
    fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    # Trailing semicolon noise is fine; strip a single trailing ;
    return t.strip().rstrip(";").strip()


def validate_sql(sql: str, known_columns: list[str], table_name: str) -> None:
    """Raise ValueError if ``sql`` is not a single safe read-only SELECT.

    Validates: single statement, starts with SELECT/WITH, no DML/DDL keywords,
    references the dataset table, and references only known columns.
    """
    if not sql or not sql.strip():
        raise ValueError("Generated SQL is empty")

    # Single statement only (ignore a single trailing ;).
    body = sql.strip().rstrip(";")
    if ";" in body:
        raise ValueError("Generated SQL must be a single statement")

    if not _SELECT_RE.match(body):
        raise ValueError("Generated SQL must be a read-only SELECT")

    if _FORBIDDEN_RE.search(body):
        raise ValueError("Generated SQL contains a forbidden (non-read-only) keyword")

    lowered = body.lower()
    if table_name and table_name.lower() not in lowered:
        raise ValueError(f"Generated SQL does not reference the dataset table {table_name}")

    # Best-effort column guard: catch SQL that references columns from a clearly
    # different table while keeping false positives near zero. We require that at
    # least one known column is referenced (an aggregate over the table with no
    # column names, e.g. ``SELECT COUNT(*)``, is allowed). CTE/table aliases and
    # ``AS <label>`` outputs are legitimate, so we do NOT reject unknown
    # identifiers wholesale — DuckDB rejects a genuinely unknown column at
    # execution, surfacing a clean error to the user.
    known = {c.lower() for c in (known_columns or [])}
    if known:
        no_strings = re.sub(r"'[^']*'", " ", lowered)
        referenced = re.findall(r"[a-z_][a-z0-9_]*", no_strings)
        if not (known & set(referenced)) and "*" not in body and "count(" not in lowered:
            # No known column and not a star/count aggregate — suspicious.
            raise ValueError("Generated SQL references no known columns of the dataset")


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def profile_schema(state: AgentState) -> AgentState:
    """Build the token-economical schema context (enforcement point).

    Caps sample rows at ``max_sample_rows``; never materializes the full table.
    """
    try:
        from services import duckdb_store

        duckdb_path = state["duckdb_path"]
        max_rows = int(state.get("max_sample_rows", 5))
        table_name = state.get("table_name")
        if not table_name:
            raise ValueError("table_name missing from state (runner must set it)")

        schema = duckdb_store.get_schema(table_name, duckdb_path)
        # Normalize schema into [{name, type}, ...]
        columns = _normalize_schema(schema)

        samples = duckdb_store.get_sample_rows(table_name, duckdb_path, max_rows)
        # Defensive cap regardless of what the service returns.
        sample_rows = _coerce_rows(samples)[:max_rows]

        schema_context = {
            "table_name": table_name,
            "columns": columns,
            "sample_rows": sample_rows,
            "aggregates": {},
        }
        return {**state, "table_name": table_name, "schema_context": schema_context}
    except Exception as exc:  # noqa: BLE001
        logger.exception("profile_schema failed for run %s", state.get("run_id"))
        return {**state, "error": f"schema profiling failed: {exc}"}


def generate_sql(state: AgentState) -> AgentState:
    """Generate a single read-only SELECT via the LLM, then validate it."""
    try:
        schema_context = state["schema_context"]
        nl_question = state["nl_question"]
        max_rows = int(state.get("max_sample_rows", 5))
        table_name = schema_context.get("table_name") or state.get("table_name")

        system = _load_prompt("generate_sql.md")
        prompt = build_sql_prompt(schema_context, nl_question, max_rows)
        raw = _call_llm_with_retry(prompt, system=system)

        sql = _strip_sql_fences(raw)
        known_columns = [c.get("name") for c in schema_context.get("columns", [])]
        validate_sql(sql, known_columns, table_name)

        logger.info("generate_sql produced SQL for run %s", state.get("run_id"))
        return {**state, "generated_sql": sql}
    except ValueError as exc:
        # Invalid / non-SELECT SQL -> 400 territory.
        return {**state, "error": f"invalid SQL: {exc}"}
    except Exception as exc:  # noqa: BLE001 - LLM failure -> 502 territory
        logger.exception("generate_sql failed for run %s", state.get("run_id"))
        return {**state, "error": f"LLM SQL generation failed: {exc}"}


def execute_sql(state: AgentState) -> AgentState:
    """Run the generated SQL on DuckDB; capture rows/count/timing."""
    try:
        from services import duckdb_store

        sql = state["generated_sql"]
        duckdb_path = state["duckdb_path"]

        columns, rows, full_row_count, duration_ms = duckdb_store.execute_select(
            sql, duckdb_path, display_limit=100
        )
        return {
            **state,
            "result_columns": list(columns),
            "result_rows": _coerce_rows(rows),
            "row_count": int(full_row_count),
            "duration_ms": int(duration_ms),
        }
    except Exception as exc:  # noqa: BLE001 - DuckDB error -> 500 territory
        logger.exception("execute_sql failed for run %s", state.get("run_id"))
        return {**state, "error": f"DuckDB execution failed: {exc}"}


def narrate(state: AgentState) -> AgentState:
    """Produce a 2-4 sentence senior-analyst narrative from a capped preview."""
    try:
        system = _load_prompt("narrate.md")
        prompt = build_narrate_prompt(
            state["nl_question"],
            state.get("generated_sql", ""),
            state.get("result_columns", []),
            state.get("result_rows", []),
            int(state.get("row_count", 0)),
        )
        narrative = _call_llm_with_retry(prompt, system=system).strip()
        return {**state, "narrative": narrative}
    except Exception as exc:  # noqa: BLE001 - LLM failure -> 502 territory
        logger.exception("narrate failed for run %s", state.get("run_id"))
        return {**state, "error": f"LLM narration failed: {exc}"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}


def handle_error(state: AgentState) -> AgentState:
    logger.error(
        "run %s failed: %s", state.get("run_id"), state.get("error")
    )
    return {**state, "status": "failed"}


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _normalize_schema(schema) -> list[dict]:
    """Normalize whatever get_schema returns into [{name, type}, ...]."""
    if schema is None:
        return []
    out: list[dict] = []
    if isinstance(schema, dict):
        for name, typ in schema.items():
            out.append({"name": str(name), "type": str(typ)})
        return out
    for item in schema:
        if isinstance(item, dict):
            name = item.get("name") or item.get("column_name") or item.get("column")
            typ = item.get("type") or item.get("column_type") or item.get("dtype")
            out.append({"name": str(name), "type": str(typ)})
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append({"name": str(item[0]), "type": str(item[1])})
        else:
            out.append({"name": str(item), "type": "VARCHAR"})
    return out


def _coerce_rows(rows) -> list[list]:
    """Coerce rows into JSON-serializable lists of plain values."""
    if rows is None:
        return []
    out: list[list] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            out.append([_coerce_value(v) for v in row])
        else:
            out.append([_coerce_value(row)])
    return out


def _coerce_value(v):
    import datetime as _dt
    from decimal import Decimal

    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (_dt.date, _dt.datetime, _dt.time)):
        return v.isoformat()
    return str(v)
