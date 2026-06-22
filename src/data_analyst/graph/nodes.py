import json
import re
import time

from data_analyst.db.models import AuditLogEntryRow, DatasetRow, SessionRow
from data_analyst.db.session import create_db_session
from data_analyst.graph.prompts import load_prompt
from data_analyst.graph.state import AgentState
from data_analyst.llm import get_llm_client
from data_analyst.observability import get_logger
from data_analyst.tools import duck

log = get_logger("data_analyst.graph")

_FRIENDLY_ERROR = (
    "I couldn't answer that question. {detail} "
    "Try rephrasing, or check that the right datasets are loaded."
)


def _datasets_block(contexts: list[dict], *, include_samples: bool) -> str:
    parts: list[str] = []
    for ctx in contexts:
        schema = ", ".join(f"{c['name']} {c['type']}" for c in ctx.get("schema", []))
        table = ctx["duckdb_table"]
        block = (
            f'SQL table name (use this EXACT name in FROM/JOIN): "{table}"\n'
            f"  (human label, NOT a table name: {ctx['name']})\n"
            f"  <table>{table}</table>\n"
            f"  columns: {schema}"
        )
        if include_samples and ctx.get("sample_rows"):
            block += f"\n  sample_rows: {json.dumps(ctx['sample_rows'], default=str)}"
        parts.append(block)
    return "\n".join(parts)


def node_plan(state: AgentState) -> AgentState:
    contexts = state.get("dataset_contexts", [])
    if not contexts:
        return {**state, "error": "No datasets are loaded in this session."}
    all_tables = [c["duckdb_table"] for c in contexts]
    try:
        client = get_llm_client()
        prompt = load_prompt("plan").format(
            datasets_block=_datasets_block(contexts, include_samples=False),
            question=state["question"],
        )
        raw = client.complete(prompt, model=client.default_model)
        parsed = _safe_json(raw)
        relevant = parsed.get("relevant_tables") or all_tables
        relevant = [t for t in relevant if t in all_tables] or all_tables
        complexity = parsed.get("complexity", "routine")
        return {**state, "relevant_tables": relevant, "complexity": complexity}
    except Exception as exc:  # noqa: BLE001 — node must not crash the run
        log.error("node_plan.error", error=str(exc), session_id=state.get("session_id"))
        return {**state, "error": f"Planning failed: {exc}"}


def node_generate_sql(state: AgentState) -> AgentState:
    contexts = state.get("dataset_contexts", [])
    relevant = set(state.get("relevant_tables") or [])
    filtered = [c for c in contexts if c["duckdb_table"] in relevant] or contexts
    try:
        client = get_llm_client()
        model = client.model_for(state.get("complexity", "routine"))
        prompt = load_prompt("generate_sql").format(
            datasets_block=_datasets_block(filtered, include_samples=True),
            question=state["question"],
        )
        sql = _strip_sql(client.complete(prompt, model=model))
        return {**state, "generated_sql": sql}
    except Exception as exc:  # noqa: BLE001
        log.error("node_generate_sql.error", error=str(exc))
        return {**state, "error": f"SQL generation failed: {exc}"}


def node_execute_sql(state: AgentState) -> AgentState:
    sql = state.get("generated_sql") or ""
    started = time.perf_counter()
    try:
        result = duck.run_query(sql)
        duration_ms = int((time.perf_counter() - started) * 1000)
        _write_audit(
            state, sql=sql, row_count=len(result.rows),
            duration_ms=duration_ms, status="success", error_message=None,
        )
        return {
            **state,
            "generated_sql": sql,
            "result_columns": result.columns,
            "result_rows": result.rows,
            "row_count": len(result.rows),
            "duration_ms": duration_ms,
        }
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.error("node_execute_sql.error", error=str(exc), retried=state.get("retried"))

        repaired = _repair_table_names(sql, state.get("dataset_contexts", []))
        if repaired and repaired != sql:
            try:
                result = duck.run_query(repaired)
                duration_ms = int((time.perf_counter() - started) * 1000)
                log.info("node_execute_sql.repaired", session_id=state.get("session_id"))
                _write_audit(
                    state, sql=repaired, row_count=len(result.rows),
                    duration_ms=duration_ms, status="success", error_message=None,
                )
                return {
                    **state,
                    "generated_sql": repaired,
                    "result_columns": result.columns,
                    "result_rows": result.rows,
                    "row_count": len(result.rows),
                    "duration_ms": duration_ms,
                }
            except Exception as repair_exc:  # noqa: BLE001
                log.error("node_execute_sql.repair_failed", error=str(repair_exc))

        if not state.get("retried"):
            return {**state, "retried": True, "error": f"SQL execution failed: {exc}"}
        _write_audit(
            state, sql=sql, row_count=None, duration_ms=duration_ms,
            status="error", error_message=str(exc),
        )
        return {**state, "error": f"SQL execution failed: {exc}", "duration_ms": duration_ms}


def node_summarize(state: AgentState) -> AgentState:
    try:
        client = get_llm_client()
        preview = _result_preview(
            state.get("result_columns") or [], state.get("result_rows") or []
        )
        prompt = load_prompt("summarize").format(
            question=state["question"], result_preview=preview
        )
        answer = client.complete(prompt, model=client.default_model)
        return {**state, "answer_text": answer}
    except Exception as exc:  # noqa: BLE001
        log.error("node_summarize.error", error=str(exc))
        return {**state, "error": f"Summarization failed: {exc}"}


def node_finalize(state: AgentState) -> AgentState:
    from data_analyst.db.models import MessageRow

    with create_db_session() as session:
        session.add(
            MessageRow(
                session_id=state["session_id"],
                role="assistant",
                content=state.get("answer_text") or "",
                generated_sql=state.get("generated_sql"),
                result_table_json={
                    "columns": state.get("result_columns") or [],
                    "rows": state.get("result_rows") or [],
                },
            )
        )
        sess = session.get(SessionRow, state["session_id"])
        if sess is not None:
            from datetime import datetime, timezone

            sess.updated_at = datetime.now(timezone.utc)
    log.info(
        "run.complete",
        session_id=state.get("session_id"),
        row_count=state.get("row_count"),
        duration_ms=state.get("duration_ms"),
    )
    return {**state, "status": "completed"}


def node_handle_error(state: AgentState) -> AgentState:
    detail = state.get("error") or "Unknown error."
    log.error("run.failed", session_id=state.get("session_id"), error=detail)

    if not _audit_exists_for_run(state):
        _write_audit(
            state, sql=state.get("generated_sql"), row_count=None,
            duration_ms=state.get("duration_ms") or 0,
            status="error", error_message=detail,
        )

    answer = _FRIENDLY_ERROR.format(detail=detail)
    from data_analyst.db.models import MessageRow

    with create_db_session() as session:
        session.add(
            MessageRow(
                session_id=state["session_id"],
                role="assistant",
                content=answer,
                generated_sql=state.get("generated_sql"),
            )
        )
    return {**state, "answer_text": answer, "status": "failed"}


# --- helpers ---------------------------------------------------------------


def _write_audit(state, *, sql, row_count, duration_ms, status, error_message) -> None:
    try:
        with create_db_session() as session:
            entry = AuditLogEntryRow(
                session_id=state["session_id"],
                nl_prompt=state.get("question"),
                generated_sql=sql,
                row_count=row_count,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message,
            )
            session.add(entry)
            session.flush()
            state["audit_entry_id"] = entry.id
    except Exception as exc:  # noqa: BLE001 — audit write is best-effort
        log.error("audit.write_failed", error=str(exc))


def _audit_exists_for_run(state) -> bool:
    return state.get("audit_entry_id") is not None


def _repair_table_names(sql: str, contexts: list[dict]) -> str:
    """Deterministically rewrite display-name table refs to real DuckDB tables.

    Safety net for when the model uses a dataset's human label (e.g. ``fifa``)
    instead of its real session-scoped table (e.g. ``s1_fifa``). Only whole-word,
    not-already-correct identifiers are remapped; string literals are left alone.
    """
    real_tables = {c["duckdb_table"] for c in contexts}
    out = sql
    for ctx in contexts:
        real = ctx["duckdb_table"]
        aliases = {ctx.get("name", ""), duck.sanitize_table_name(ctx.get("name", ""))}
        for alias in aliases:
            if not alias or alias in real_tables or alias == real:
                continue
            pattern = re.compile(
                rf'(?<!["\w])"?{re.escape(alias)}"?(?![\w"])', re.IGNORECASE
            )
            out = pattern.sub(f'"{real}"', out)
    return out


def _safe_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("{") :]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _strip_sql(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    return raw.rstrip(";").strip()


def _result_preview(columns: list[str], rows: list[list], limit: int = 20) -> str:
    head = rows[:limit]
    return json.dumps({"columns": columns, "rows": head}, default=str)


def list_dataset_contexts(session_id: int) -> list[dict]:
    """Build the token-economy context payload (schema + cached samples) for a session."""
    with create_db_session() as session:
        rows = (
            session.query(DatasetRow)
            .filter(DatasetRow.session_id == session_id)
            .all()
        )
        return [
            {
                "name": r.name,
                "duckdb_table": r.duckdb_table,
                "schema": r.schema_json,
                "sample_rows": r.sample_rows_json,
            }
            for r in rows
        ]
