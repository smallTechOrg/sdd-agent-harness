import time

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session, init_db
from db.models import RunRow
from observability.events import get_logger

_log = get_logger("runner")


def run_agent(input_text: str, conversation_id: str = "") -> str:
    init_db()

    with create_db_session() as session:
        run = RunRow(input_text=input_text)
        session.add(run)
        session.flush()
        run_id = run.id

    _log.info("run.start", run_id=run_id)
    t0 = time.monotonic()

    initial: AgentState = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "input_text": input_text,
        "error": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "iterations": 0,
        "messages": [],
        "node_trace": [],
    }
    final = agentic_ai.invoke(initial)

    latency_ms = round((time.monotonic() - t0) * 1000, 2)
    _log.info(
        "run.persisted",
        run_id=run_id,
        status=final.get("status", "completed"),
        latency_ms=latency_ms,
        tokens_in=final.get("tokens_in", 0),
        tokens_out=final.get("tokens_out", 0),
        cost_usd=final.get("cost_usd", 0.0),
    )

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = final.get("status", "completed")
        run.output_text = final.get("output_text")
        run.error_message = final.get("error")
        run.tokens_in = final.get("tokens_in", 0)
        run.tokens_out = final.get("tokens_out", 0)
        run.cost_usd = final.get("cost_usd", 0.0)
        run.latency_ms = latency_ms
        run.model = final.get("model")
        run.node_trace = final.get("node_trace", [])
        run.guard_code = final.get("guard_code")

    return run_id
