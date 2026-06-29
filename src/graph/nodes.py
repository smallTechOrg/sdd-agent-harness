"""Analysis graph nodes.

Privacy boundary (hard invariant): the only node that touches raw data is
``execute_sql``, and it runs entirely inside local DuckDB. The LLM-calling nodes
(``generate_sql``, ``answer``) receive ONLY the schema, the question, prior
SQL/error text, and small aggregate result rows — never raw source rows.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from graph.state import AgentState
from llm.client import LLMClient
from analysis.duckdb_engine import run_query
from analysis.charts import choose_chart
from analysis.summary import summarize_result
from observability.events import get_logger

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analysis.md"
_FOLLOWUPS_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "followups.md"

# Number of suggested follow-up questions to keep (capability: 2-3).
_FOLLOWUPS_MIN = 2
_FOLLOWUPS_MAX = 3

# Bounded retry for transient Gemini errors (timeout / 429 / 5xx).
_LLM_MAX_ATTEMPTS = 3
_LLM_BACKOFF_SECONDS = 1.5

log = get_logger("graph")


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def _call_llm(prompt: str, *, system: str) -> str:
    """Call Gemini with bounded backoff on transient failure.

    Raises the last exception if all attempts fail (caller maps to fatal error).
    """
    last_exc: Exception | None = None
    for attempt in range(1, _LLM_MAX_ATTEMPTS + 1):
        try:
            return LLMClient().call_model(prompt, system=system)
        except Exception as exc:  # provider/transport errors
            last_exc = exc
            if attempt < _LLM_MAX_ATTEMPTS:
                time.sleep(_LLM_BACKOFF_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc


_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def parse_sql(raw: str) -> str:
    """Extract a SQL statement from a model response.

    Strips ```sql fences if present; otherwise returns the trimmed text. Also
    drops a trailing semicolon-free trailing prose by keeping content up to the
    fence. Designed to be tolerant of the model adding a fenced block.
    """
    if raw is None:
        return ""
    match = _SQL_FENCE_RE.search(raw)
    sql = match.group(1) if match else raw
    return sql.strip()


def _format_schema(schema: list[dict]) -> str:
    return "\n".join(f"- {c['name']} ({c['type']})" for c in (schema or []))


def generate_sql(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    attempts = state.get("sql_attempts", 0)
    schema = state.get("schema", [])
    question = state.get("question", "")

    parts = [
        "Table: data",
        "Schema (column name and DuckDB type):",
        _format_schema(schema),
        "",
        f"Question: {question}",
    ]
    prior_sql = state.get("sql")
    prior_error = state.get("sql_error")
    if prior_sql and prior_error:
        parts += [
            "",
            "Your previous DuckDB SQL failed. Correct it.",
            f"Previous SQL:\n{prior_sql}",
            f"DuckDB error (verbatim):\n{prior_error}",
        ]
    parts += ["", "Write the DuckDB SQL query (SQL only)."]
    prompt = "\n".join(parts)

    try:
        raw = _call_llm(prompt, system=_load_system_prompt())
    except Exception as exc:
        log.error("generate_sql.failed", run_id=run_id, error=str(exc))
        return {**state, "error": f"SQL generation failed: {exc}"}

    sql = parse_sql(raw)
    new_attempts = attempts + 1
    log.info(
        "generate_sql.ok",
        run_id=run_id,
        attempt=new_attempts,
        sql=sql,
        retried_after_error=bool(prior_error),
    )
    if not sql:
        return {**state, "error": "Model returned no SQL."}
    return {**state, "sql": sql, "sql_attempts": new_attempts}


def execute_sql(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    sql = state.get("sql") or ""
    dataset_path = state.get("dataset_path") or ""

    rows, error = run_query(dataset_path, sql)
    if error is not None:
        log.warning(
            "execute_sql.error",
            run_id=run_id,
            attempt=state.get("sql_attempts"),
            duckdb_error=error,
        )
        # Not fatal — routes to the retry-on-SQL-error edge.
        return {**state, "sql_error": error, "result_rows": None}

    log.info(
        "execute_sql.ok",
        run_id=run_id,
        result_row_count=len(rows),
    )
    # Success clears the prior SQL error.
    return {**state, "result_rows": rows, "sql_error": None}


def answer(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    schema = state.get("schema", [])
    question = state.get("question", "")
    sql = state.get("sql") or ""
    result_rows = state.get("result_rows") or []

    prompt = "\n".join(
        [
            "Table: data",
            "Schema (column name and DuckDB type):",
            _format_schema(schema),
            "",
            f"Question: {question}",
            "",
            "The DuckDB SQL that was run:",
            sql,
            "",
            "Aggregate result rows (JSON) — the only data you may use:",
            json.dumps(result_rows),
            "",
            "Write a concise plain-English analyst answer stating the key "
            "number(s). If the result is empty or ambiguous, say so and flag any "
            "best guess. Do not invent numbers not present in the result.",
        ]
    )

    try:
        text = _call_llm(prompt, system=_load_system_prompt())
    except Exception as exc:
        log.error("answer.failed", run_id=run_id, error=str(exc))
        return {**state, "error": f"Answer generation failed: {exc}"}

    answer_text = (text or "").strip()
    if not answer_text:
        return {**state, "error": "Model returned an empty answer."}

    flagged = "best guess" in answer_text.lower() or "best-guess" in answer_text.lower()
    log.info("answer.ok", run_id=run_id, flagged=flagged)
    return {**state, "answer_text": answer_text, "flagged": flagged}


def _load_followups_prompt() -> str:
    return _FOLLOWUPS_PROMPT_PATH.read_text(encoding="utf-8").strip()


def parse_followups(raw: str) -> list[str]:
    """Parse a model response into 2-3 follow-up questions.

    One question per line; strips numbering/bullets and blank lines. Caps at
    ``_FOLLOWUPS_MAX``. Returns an empty list if nothing usable was produced.
    """
    if not raw:
        return []
    questions: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        # Strip a leading bullet / number marker ("1.", "1)", "-", "*").
        text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", text).strip()
        # Strip wrapping quotes a model sometimes adds.
        text = text.strip('"').strip("'").strip()
        if text:
            questions.append(text)
        if len(questions) >= _FOLLOWUPS_MAX:
            break
    return questions


def suggest_followups(state: AgentState) -> AgentState:
    """Suggest 2-3 follow-up questions from schema + aggregate result only.

    NON-FATAL: any failure (LLM error, too few parsed) logs and sets
    ``followups=None`` and falls through to ``finalize``. A follow-up failure
    must never fail the run or fabricate anything. Receives schema + question +
    aggregate result rows only — never raw source rows.
    """
    run_id = state.get("run_id")
    schema = state.get("schema", [])
    question = state.get("question", "")
    result_rows = state.get("result_rows") or []

    prompt = "\n".join(
        [
            "Table: data",
            "Schema (column name and DuckDB type):",
            _format_schema(schema),
            "",
            f"The user just asked: {question}",
            "",
            "Aggregate result rows (JSON) — the only data you may use:",
            json.dumps(result_rows),
            "",
            "Suggest 2-3 follow-up questions, one per line, no numbering.",
        ]
    )

    try:
        raw = _call_llm(prompt, system=_load_followups_prompt())
    except Exception as exc:
        log.warning("suggest_followups.failed", run_id=run_id, error=str(exc))
        return {**state, "followups": None}

    parsed = parse_followups(raw)
    if len(parsed) < _FOLLOWUPS_MIN:
        log.warning(
            "suggest_followups.too_few", run_id=run_id, parsed_count=len(parsed)
        )
        return {**state, "followups": None}

    log.info("suggest_followups.ok", run_id=run_id, count=len(parsed))
    return {**state, "followups": parsed}


def finalize(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    answer_text = state.get("answer_text") or ""
    sql = state.get("sql") or ""
    schema = state.get("schema", [])
    result_rows = state.get("result_rows")
    output_text = f"{answer_text}\n\nSQL:\n{sql}".strip()

    # Deterministic enrichment from the aggregate result only (no LLM, no raw
    # rows). Each is best-effort and never fails the run.
    question = state.get("question", "")
    try:
        chart = choose_chart(question, result_rows, schema)
    except Exception as exc:  # defensive
        log.warning("finalize.chart_error", run_id=run_id, error=str(exc))
        chart = None
    try:
        summary_table = summarize_result(result_rows, schema)
    except Exception as exc:  # defensive
        log.warning("finalize.summary_error", run_id=run_id, error=str(exc))
        summary_table = None

    log.info(
        "finalize.ok",
        run_id=run_id,
        status="completed",
        has_chart=chart is not None,
        has_summary=summary_table is not None,
        followups_count=len(state.get("followups") or []),
    )
    return {
        **state,
        "status": "completed",
        "output_text": output_text,
        "chart": chart,
        "summary_table": summary_table,
    }


def handle_error(state: AgentState) -> AgentState:
    run_id = state.get("run_id")
    error = state.get("error") or state.get("sql_error") or "Unknown error"
    log.error("handle_error", run_id=run_id, error=error, status="failed")
    return {**state, "status": "failed", "error": error}
