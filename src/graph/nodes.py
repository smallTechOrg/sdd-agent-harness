import re
import time
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import text
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from graph.state import AgentState
from db.session import create_db_session
from config.settings import get_settings
from observability.events import get_logger

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "transform.md"
_log = get_logger("nodes")

_SQL_DANGER_PATTERN = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE)\b',
    re.IGNORECASE,
)


def is_sql_safe(sql: str) -> bool:
    """Return True if sql contains only SELECT logic (no DDL/DML)."""
    return _SQL_DANGER_PATTERN.search(sql) is None


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


class SQLOutput(BaseModel):
    sql: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def schema_introspection(state: AgentState) -> AgentState:
    _log.info("schema_introspection.enter", table_name=state.get("table_name"))
    try:
        table_name = state["table_name"]
        with create_db_session() as session:
            result = session.execute(text(f"PRAGMA table_info({table_name})"))
            rows = result.mappings().all()
        schema = [{"name": row["name"], "type": row["type"]} for row in rows]
        _log.info("schema_introspection.done", col_count=len(schema))
        return {**state, "schema": schema}
    except Exception as exc:
        _log.error("schema_introspection.error", error=str(exc))
        return {**state, "error": str(exc)}


def sql_generation(state: AgentState) -> AgentState:
    _log.info("sql_generation.enter", question=state.get("question", "")[:80])
    try:
        settings = get_settings()
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.gemini_api_key,
            temperature=0,
            request_timeout=30,
        )
        structured_llm = llm.with_structured_output(SQLOutput)

        prompt_template = _load_prompt()
        schema_text = "\n".join(
            f"  {col['name']} {col['type']}" for col in state.get("schema", [])
        )
        prompt = (
            f"{prompt_template}\n\n"
            f"Table: {state['table_name']}\n"
            f"Schema:\n{schema_text}\n\n"
            f"Question: {state['question']}"
        )

        result: SQLOutput = structured_llm.invoke([HumanMessage(content=prompt)])
        sql = result.sql.strip()
        _log.info("sql_generation.done", sql=sql[:200])
        return {**state, "sql": sql}
    except Exception as exc:
        _log.error("sql_generation.error", error=str(exc))
        return {**state, "error": str(exc)}


def sql_execution(state: AgentState) -> AgentState:
    _log.info("sql_execution.enter")
    try:
        sql = state["sql"]

        # Safety guard: block DDL/DML
        if not is_sql_safe(sql):
            msg = "SQL safety violation: only SELECT queries are permitted."
            _log.warning("sql_execution.safety_violation", sql=sql[:200])
            return {**state, "error": msg}

        t0 = time.monotonic()
        with create_db_session() as session:
            result = session.execute(text(sql))
            rows = list(result.mappings().all())
        duration_ms = int((time.monotonic() - t0) * 1000)
        _log.info("sql_execution.done", row_count=len(rows), duration_ms=duration_ms)
        return {**state, "rows": [dict(r) for r in rows]}
    except Exception as exc:
        _log.error("sql_execution.error", error=str(exc))
        return {**state, "error": str(exc)}


def chart_selection(state: AgentState) -> AgentState:
    _log.info("chart_selection.enter")
    try:
        rows = state.get("rows") or []
        question = state.get("question", "")
        title = question[:60]

        if not rows:
            chart_spec = {
                "type": "empty",
                "message": "Query returned no rows.",
                "data": [],
                "title": title,
            }
            _log.info("chart_selection.done", chart_type="empty", data_points=0)
            return {**state, "chart_spec": chart_spec}

        keys = list(rows[0].keys())

        def _is_numeric(col: str) -> bool:
            for row in rows:
                v = row.get(col)
                if v is None or v == "":
                    continue
                try:
                    float(v)
                    return True
                except (TypeError, ValueError):
                    return False
            return False

        def _is_date_like(col: str) -> bool:
            for row in rows:
                v = row.get(col)
                if v and isinstance(v, str) and ("-" in v or "/" in v):
                    parts = v.replace("/", "-").split("-")
                    if len(parts) >= 2 and all(p.strip().isdigit() for p in parts[:2]):
                        return True
            return False

        numeric_cols = [k for k in keys if _is_numeric(k)]
        string_cols = [k for k in keys if k not in numeric_cols]

        chart_type = "bar"
        x_key = string_cols[0] if string_cols else keys[0]
        y_key = numeric_cols[0] if numeric_cols else keys[-1]

        if len(keys) == 2 and len(numeric_cols) == 1 and len(string_cols) == 1:
            # Check for date-like string col → line
            if _is_date_like(string_cols[0]):
                chart_type = "line"
            else:
                unique_vals = {row.get(string_cols[0]) for row in rows}
                if len(unique_vals) <= 8:
                    chart_type = "pie"
                else:
                    chart_type = "bar"
        elif len(numeric_cols) >= 2:
            chart_type = "scatter"
            x_key = numeric_cols[0]
            y_key = numeric_cols[1]
        elif string_cols and numeric_cols:
            if _is_date_like(string_cols[0]):
                chart_type = "line"
            else:
                chart_type = "bar"

        data = [{x_key: row.get(x_key), y_key: row.get(y_key)} for row in rows]

        if chart_type == "pie":
            chart_spec = {
                "type": "pie",
                "title": title,
                "nameKey": x_key,
                "valueKey": y_key,
                "data": [{x_key: row.get(x_key), y_key: row.get(y_key)} for row in rows],
            }
        elif chart_type == "scatter":
            chart_spec = {
                "type": "scatter",
                "title": title,
                "xKey": x_key,
                "yKey": y_key,
                "data": data,
            }
        else:
            chart_spec = {
                "type": chart_type,
                "title": title,
                "xKey": x_key,
                "yKey": y_key,
                "data": data,
            }

        _log.info("chart_selection.done", chart_type=chart_type, data_points=len(data))
        return {**state, "chart_spec": chart_spec}
    except Exception as exc:
        _log.error("chart_selection.error", error=str(exc))
        return {**state, "chart_spec": {"type": "empty", "message": str(exc), "data": [], "title": ""}}


def insight_generation(state: AgentState) -> AgentState:
    _log.info("insight_generation.enter")
    try:
        settings = get_settings()
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
            request_timeout=30,
        )

        question = state.get("question", "")
        rows = state.get("rows") or []
        chart_spec = state.get("chart_spec") or {}
        chart_type = chart_spec.get("type", "unknown")

        if len(rows) <= 20:
            if rows:
                headers = list(rows[0].keys())
                header_row = " | ".join(headers)
                separator = " | ".join(["---"] * len(headers))
                data_rows = "\n".join(
                    " | ".join(str(row.get(h, "")) for h in headers) for row in rows
                )
                table_text = f"| {header_row} |\n| {separator} |\n" + "\n".join(
                    f"| {' | '.join(str(row.get(h, '')) for h in headers)} |" for row in rows
                )
            else:
                table_text = "(no rows returned)"
        else:
            # Column stats summary
            headers = list(rows[0].keys()) if rows else []
            stats_lines = []
            for col in headers:
                values = [row.get(col) for row in rows if row.get(col) is not None]
                stats_lines.append(f"- {col}: {len(values)} non-null values")
            table_text = f"(showing stats for {len(rows)} rows)\n" + "\n".join(stats_lines)

        prompt = (
            f"Question: {question}\n\n"
            f"Chart type: {chart_type}\n\n"
            f"Data:\n{table_text}\n\n"
            f"Write a concise 2-3 sentence plain-English insight that directly answers the question "
            f"based on the data above. Be specific with numbers."
        )

        result = llm.invoke([HumanMessage(content=prompt)])
        insight = result.content.strip()
        _log.info("insight_generation.done", insight_len=len(insight))
        return {**state, "insight": insight}
    except Exception as exc:
        _log.error("insight_generation.error", error=str(exc))
        return {**state, "error": str(exc)}


def handle_error(state: AgentState) -> AgentState:
    _log.error("handle_error", error=state.get("error"))
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}
