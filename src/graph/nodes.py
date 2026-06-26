"""LangGraph nodes for the local data-analyst pipeline.

Pipeline: profile_csv (local) → generate_code (Gemini) → execute_code (local
sandbox) → explain_result (Gemini) → finalize, with handle_error as the failure
terminal.

CONSTRAINT (non-negotiable): only the schema, the capped sample (≤20 rows), the
row count, the question, and — for explain — the SMALL computed result ever go
into a prompt. The full DataFrame and the raw csv_text NEVER enter any prompt.
"""

from __future__ import annotations

import json
from pathlib import Path

from analysis.profiler import ProfileError, profile
from analysis.sandbox import SandboxError, run_sandbox
from analysis.sql_executor import SQLExecutorError, run_sql
from config.settings import get_settings
from graph.state import AgentState
from llm.client import LLMClient

_PROMPTS = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


def _strip_code_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from an LLM code reply."""
    s = (text or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        # drop the opening fence (``` or ```python)
        lines = lines[1:]
        # drop the closing fence if present
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def profile_csv(state: AgentState) -> AgentState:
    try:
        settings = get_settings()
        df, schema, sample_rows, row_count = profile(state["csv_text"], settings)
        return {
            **state,
            "df": df,
            "schema": schema,
            "sample_rows": sample_rows,
            "row_count": row_count,
        }
    except ProfileError as exc:
        return {**state, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - any parse failure is a clean error
        return {**state, "error": f"Couldn't read that as a CSV: {exc}"}


def generate_code(state: AgentState) -> AgentState:
    try:
        # Determine the mode (default to pandas for backward compatibility)
        mode = state.get("mode", "pandas")

        # Choose the appropriate system prompt
        if mode == "sql":
            system = _load_prompt("generate_sql.md")
        else:
            system = _load_prompt("generate_code.md")

        # Build the user message from schema + capped sample + row count + question ONLY.
        user_msg = (
            f"SCHEMA (columns and dtypes):\n{json.dumps(state['schema'])}\n\n"
            f"SAMPLE (first {len(state['sample_rows'])} rows — preview only, not the full data):\n"
            f"{json.dumps(state['sample_rows'], default=str)}\n\n"
            f"ROW COUNT (full dataset): {state['row_count']}\n\n"
            f"QUESTION: {state['question']}"
        )
        raw = LLMClient().call_model(user_msg, system=system)
        code = _strip_code_fences(raw)
        if not code:
            return {**state, "error": "The model did not return any code to run."}
        return {**state, "generated_code": code}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Failed to generate the analysis code: {exc}"}


def execute_code(state: AgentState) -> AgentState:
    try:
        settings = get_settings()
        mode = state.get("mode", "pandas")

        if mode == "sql":
            # SQL mode: execute the generated SQL query
            result_table, truncated = run_sql(
                state["generated_code"],
                state["df"],
                table_name="data",
                timeout=settings.exec_timeout,
                max_rows=settings.max_result_rows,
            )
            return {
                **state,
                "result_table": result_table,
                "result_scalar": None,
                "truncated": truncated,
            }
        else:
            # Pandas mode: execute the generated pandas code (original path)
            result_table, result_scalar, truncated = run_sandbox(
                state["generated_code"], state["df"], settings
            )
            return {
                **state,
                "result_table": result_table,
                "result_scalar": result_scalar,
                "truncated": truncated,
            }
    except SQLExecutorError as exc:
        return {**state, "error": str(exc)}
    except SandboxError as exc:
        return {**state, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"The generated code failed to run: {exc}"}


def _parse_explanation(text: str) -> tuple[str, str]:
    """Parse the ANSWER:/EXPLANATION: format; fall back gracefully."""
    answer = ""
    explanation = ""
    for line in (text or "").splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("ANSWER:"):
            answer = stripped[len("ANSWER:"):].strip()
        elif upper.startswith("EXPLANATION:"):
            explanation = stripped[len("EXPLANATION:"):].strip()
        elif explanation:
            # continuation lines of a multi-line explanation
            explanation = f"{explanation} {stripped}".strip()
    if not answer and not explanation:
        # Model ignored the format — use the whole text for both.
        whole = (text or "").strip()
        answer = whole.split("\n", 1)[0].strip()
        explanation = whole
    elif not answer:
        answer = explanation
    elif not explanation:
        explanation = answer
    return answer, explanation


def _result_for_prompt(state: AgentState) -> str:
    """A compact, JSON-safe view of the SMALL computed result for the explain prompt."""
    if state.get("result_table") is not None:
        return json.dumps(state["result_table"], default=str)
    return json.dumps({"value": state.get("result_scalar")}, default=str)


def explain_result(state: AgentState) -> AgentState:
    try:
        system = _load_prompt("explain_result.md")
        user_msg = (
            f"QUESTION: {state['question']}\n\n"
            f"CODE:\n{state['generated_code']}\n\n"
            f"RESULT:\n{_result_for_prompt(state)}"
        )
        raw = LLMClient().call_model(user_msg, system=system)
        answer, explanation = _parse_explanation(raw)
        return {**state, "answer": answer, "explanation": explanation}
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Failed to explain the result: {exc}"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}


def handle_error(state: AgentState) -> AgentState:
    return {**state, "status": "failed"}
