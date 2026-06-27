"""DataChat graph nodes.

The privacy boundary is enforced here: ONLY ``plan_compute`` and
``phrase_answer`` import/call the LLM, and each calls ``assert_no_raw_rows`` on
its outgoing payload immediately before the LLM call. Every other node
(``profile_data``, ``execute_local``, ``finalize``, ``handle_error``) is purely
local and never touches the LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph.state import AgentState
from tools.compute import assert_no_raw_rows, run_aggregation
from tools.profile import build_schema_summary

_PROMPTS = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


def _parse_llm_json(text: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating markdown fences.

    Gemini sometimes wraps JSON in ```json ... ``` fences; strip them. Falls
    back to extracting the first {...} block if extra prose leaks in.
    """
    s = (text or "").strip()
    if s.startswith("```"):
        # drop the opening fence line (``` or ```json) and the trailing fence
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.rstrip().endswith("```"):
            s = s.rsplit("```", 1)[0]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
        raise


# --- profile_data ------------------------------------------------------------

def profile_data(state: AgentState) -> AgentState:
    """Local schema profiling. No LLM."""
    try:
        summary = build_schema_summary(state["dataset_id"])
        return {**state, "schema_summary": summary}
    except Exception as exc:
        return {**state, "error": f"PROFILE_FAILED: {exc}"}


# --- plan_compute (LLM) ------------------------------------------------------

def plan_compute(state: AgentState) -> AgentState:
    """LLM picks columns + aggregation. Payload = schema summary only."""
    try:
        schema_summary = state["schema_summary"]
        # Guard the LLM-bound payload immediately before the call.
        assert_no_raw_rows(schema_summary)

        from llm.client import LLMClient

        system = _load_prompt("plan.md")
        user = (
            "SCHEMA SUMMARY (JSON):\n"
            f"{json.dumps(schema_summary)}\n\n"
            f"QUESTION:\n{state['question']}\n\n"
            "Return ONLY the JSON plan."
        )
        raw = LLMClient().call_model(user, system=system)
        plan = _parse_llm_json(raw)
        if not isinstance(plan, dict) or not plan.get("group_by"):
            return {**state, "error": f"PLAN_INVALID: {raw!r}"}
        return {**state, "compute_plan": plan}
    except Exception as exc:
        return {**state, "error": f"LLM_UNAVAILABLE: {exc}"}


# --- execute_local -----------------------------------------------------------

def execute_local(state: AgentState) -> AgentState:
    """Run the compute plan locally over the FULL dataset. No LLM."""
    try:
        result = run_aggregation(state["compute_plan"], state["dataset_id"])
        return {**state, "aggregate_result": result}
    except Exception as exc:
        return {**state, "error": f"COMPUTE_FAILED: {exc}"}


# --- phrase_answer (LLM) -----------------------------------------------------

def phrase_answer(state: AgentState) -> AgentState:
    """LLM phrases the answer + chart. Payload = aggregate result only."""
    try:
        aggregate_result = state["aggregate_result"]
        # Guard the LLM-bound payload immediately before the call.
        assert_no_raw_rows(aggregate_result)

        from llm.client import LLMClient

        system = _load_prompt("answer.md")
        user = (
            f"QUESTION:\n{state['question']}\n\n"
            "AGGREGATE RESULT (JSON):\n"
            f"{json.dumps(aggregate_result)}\n\n"
            "Return ONLY the JSON answer."
        )
        raw = LLMClient().call_model(user, system=system)
        parsed = _parse_llm_json(raw)
        answer_text = parsed.get("answer")
        chart_spec = parsed.get("chart")
        if not answer_text or not isinstance(chart_spec, dict):
            return {**state, "error": f"PHRASE_INVALID: {raw!r}"}
        return {**state, "answer_text": answer_text, "chart_spec": chart_spec}
    except Exception as exc:
        return {**state, "error": f"LLM_UNAVAILABLE: {exc}"}


# --- finalize ----------------------------------------------------------------

def finalize(state: AgentState) -> AgentState:
    """Persist the completed QuestionRow. No LLM."""
    from db.session import create_db_session
    from db.models import QuestionRow

    run_id = state.get("run_id")
    chart_spec = state.get("chart_spec")
    if run_id:
        with create_db_session() as session:
            q = session.get(QuestionRow, run_id)
            if q is not None:
                q.answer_text = state.get("answer_text")
                q.chart_spec = json.dumps(chart_spec) if chart_spec is not None else None
                q.status = "completed"
                q.error_message = None
    return {**state, "status": "completed"}


# --- handle_error ------------------------------------------------------------

def handle_error(state: AgentState) -> AgentState:
    """Persist the failed QuestionRow. No LLM."""
    from db.session import create_db_session
    from db.models import QuestionRow

    run_id = state.get("run_id")
    if run_id:
        with create_db_session() as session:
            q = session.get(QuestionRow, run_id)
            if q is not None:
                q.status = "failed"
                q.error_message = state.get("error")
    return {**state, "status": "failed"}
