"""DataChat graph nodes.

The privacy boundary lives in the **ordering and responsibilities** of these
nodes: the only nodes that call Gemini (`plan_aggregation`,
`compose_answer_and_pick_chart`) send it schema + a small aggregate table only.
`run_local_aggregation` is the privacy firewall — it touches raw rows (via the
local pandas engine) and **never** calls an LLM.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from graph.state import AgentState
from llm.client import LLMClient
from observability.events import get_logger

# Local data layer (already built). run_plan is the only code that reads raw rows.
from data.aggregation import run_plan, MAX_ROWS

_PROMPT_DIR = Path(__file__).parent.parent / "prompts"
_log = get_logger("graph")

_VALID_AGGS = {"sum", "mean", "count", "min", "max"}
_VALID_INTENTS = {"comparison", "trend", "distribution", "single_value"}


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def _parse_json_block(text: str) -> dict:
    """Robustly extract a JSON object from an LLM response.

    Tolerates the model wrapping JSON in a ```json fence, adding prose around it,
    or emitting bare JSON. Raises ValueError if no JSON object can be parsed.
    """
    if not text or not text.strip():
        raise ValueError("LLM returned an empty response")

    candidates: list[str] = []

    # 1) Fenced ```json ... ``` (or plain ``` ... ```) block.
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())

    # 2) The first {...} span in the text.
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0).strip())

    # 3) The raw text itself.
    candidates.append(text.strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]!r}")


def _compact_schema(schema: dict) -> str:
    """Render the schema as a compact, LLM-safe string. Columns + types only."""
    columns = (schema or {}).get("columns", [])
    cols = ", ".join(f"{c['name']} ({c['dtype']})" for c in columns)
    row_count = (schema or {}).get("row_count")
    return f"columns: {cols}\nrow_count: {row_count}"


def _format_history(history: list | None) -> str:
    if not history:
        return "(no prior turns)"
    lines = [f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in history]
    return "\n".join(lines)


def _normalize_plan(plan: dict) -> dict:
    """Coerce an LLM-produced plan into the AggregationPlan contract.

    Validates enum fields and caps the limit; does not validate column names
    (the aggregation engine does that and raises on a missing column, which the
    graph routes to handle_error).
    """
    group_by = plan.get("group_by") or []
    if isinstance(group_by, str):
        group_by = [group_by]
    group_by = [str(c) for c in group_by]

    metric = plan.get("metric")
    metric = str(metric) if metric else None

    agg = str(plan.get("agg") or "count").lower()
    if agg not in _VALID_AGGS:
        raise ValueError(f"Plan has invalid agg {agg!r}; expected one of {sorted(_VALID_AGGS)}")

    intent = str(plan.get("intent") or "comparison").lower()
    if intent not in _VALID_INTENTS:
        intent = "comparison"

    sort = plan.get("sort")
    sort = sort if sort in ("asc", "desc") else None

    limit = plan.get("limit")
    limit = limit if isinstance(limit, int) and 0 < limit <= MAX_ROWS else MAX_ROWS

    return {
        "group_by": group_by,
        "metric": metric,
        "agg": agg,
        "filter": plan.get("filter"),
        "sort": sort,
        "limit": limit,
        "intent": intent,
    }


# --------------------------------------------------------------------------- #
# Node 1 — plan_aggregation (LLM; schema + history + question, NO raw rows)
# --------------------------------------------------------------------------- #
def plan_aggregation(state: AgentState) -> AgentState:
    try:
        system = _load_prompt("plan_aggregation.md")
        prompt = (
            "Schema:\n"
            f"{_compact_schema(state['schema'])}\n\n"
            "Recent conversation history:\n"
            f"{_format_history(state.get('history'))}\n\n"
            "Question:\n"
            f"{state['question']}\n\n"
            "Output the aggregation plan as a single fenced ```json block."
        )
        raw = LLMClient().call_model(prompt, system=system)
        plan = _normalize_plan(_parse_json_block(raw))
        _log.info("plan_aggregation", run_id=state.get("run_id"), plan=plan)
        return {**state, "plan": plan}
    except Exception as exc:  # noqa: BLE001 — node-level fatal => route to handle_error
        _log.error("plan_aggregation_failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"plan_aggregation: {exc}"}


# --------------------------------------------------------------------------- #
# Node 2 — run_local_aggregation (NO LLM — the privacy firewall)
# --------------------------------------------------------------------------- #
def run_local_aggregation(state: AgentState) -> AgentState:
    """PRIVACY FIREWALL: reads raw rows locally, NEVER calls an LLM."""
    try:
        result = run_plan(state["file_path"], state["plan"])
        _log.info(
            "run_local_aggregation",
            run_id=state.get("run_id"),
            rows=len(result["rows"]),
            columns=result["columns"],
        )
        return {
            **state,
            "aggregate_table": result["rows"],
            "aggregate_columns": result["columns"],
        }
    except Exception as exc:  # noqa: BLE001
        _log.error("run_local_aggregation_failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"run_local_aggregation: {exc}"}


# --------------------------------------------------------------------------- #
# Node 3 — compose_answer_and_pick_chart (LLM; aggregate table only, NO raw rows)
# --------------------------------------------------------------------------- #
def compose_answer_and_pick_chart(state: AgentState) -> AgentState:
    try:
        system = _load_prompt("compose_answer.md")
        intent = (state.get("plan") or {}).get("intent", "comparison")
        prompt = (
            "Question:\n"
            f"{state['question']}\n\n"
            f"Intent hint: {intent}\n\n"
            f"aggregate_columns: {json.dumps(state.get('aggregate_columns'))}\n\n"
            "aggregate_table (already summarized locally — these are the only "
            "data figures you have):\n"
            f"{json.dumps(state.get('aggregate_table'))}\n\n"
            "Output {answer, chart} as a single fenced ```json block."
        )
        raw = LLMClient().call_model(prompt, system=system)
        parsed = _parse_json_block(raw)
        answer = parsed.get("answer")
        if not answer or not str(answer).strip():
            raise ValueError("compose returned an empty answer")
        chart = parsed.get("chart")
        chart = chart if isinstance(chart, dict) else None
        _log.info(
            "compose_answer",
            run_id=state.get("run_id"),
            has_chart=chart is not None,
        )
        return {**state, "answer": str(answer).strip(), "chart": chart}
    except Exception as exc:  # noqa: BLE001
        _log.error("compose_answer_failed", run_id=state.get("run_id"), error=str(exc))
        return {**state, "error": f"compose_answer: {exc}"}


# --------------------------------------------------------------------------- #
# Node 4 — finalize (NO LLM): persist assistant Message + mark run completed
# --------------------------------------------------------------------------- #
def finalize(state: AgentState) -> AgentState:
    from db.session import create_db_session
    from db.models import Message, RunRow

    answer = state.get("answer") or ""
    chart = state.get("chart")
    chart_json = json.dumps(chart) if chart else None

    with create_db_session() as session:
        session.add(
            Message(
                conversation_id=state["conversation_id"],
                role="assistant",
                content=answer,
                chart_json=chart_json,
            )
        )
        run = session.get(RunRow, state.get("run_id"))
        if run is not None:
            run.status = "completed"
            run.output_text = answer
    _log.info("finalize", run_id=state.get("run_id"), conversation_id=state.get("conversation_id"))
    return {**state, "status": "completed"}


# --------------------------------------------------------------------------- #
# Node 5 — handle_error (NO LLM): persist a user-facing error Message + fail run
# --------------------------------------------------------------------------- #
def handle_error(state: AgentState) -> AgentState:
    from db.session import create_db_session
    from db.models import Message, RunRow

    error = state.get("error") or "unknown error"
    user_message = (
        "I couldn't answer that — I wasn't able to work out how to compute it "
        "from this dataset. Try rephrasing, or check the column you're asking about."
    )

    with create_db_session() as session:
        session.add(
            Message(
                conversation_id=state["conversation_id"],
                role="assistant",
                content=user_message,
                chart_json=None,
            )
        )
        run = session.get(RunRow, state.get("run_id"))
        if run is not None:
            run.status = "failed"
            run.error_message = error
    _log.error("handle_error", run_id=state.get("run_id"), error=error)
    return {**state, "answer": user_message, "chart": None, "status": "failed"}
