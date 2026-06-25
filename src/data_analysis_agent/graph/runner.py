import asyncio

import structlog

from data_analysis_agent.db.models import AgentRunRow
from data_analysis_agent.db.session import create_db_session, init_db
from data_analysis_agent.graph.agent import agent_graph
from data_analysis_agent.graph.persistence import mark_failed
from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.tools.mcp.pool import get_manager

log = structlog.get_logger()


def run_pipeline(
    query_record_id: str,
    session_id: str,
    question: str,
) -> AgentState:
    """Run one query against a session's (reused) MCP pool and return the final state.

    Stays synchronous (the HTTP handler's background thread and the integration tests call it
    unchanged) but holds the per-session lock for the whole query — the session's DuckDB
    connection is not concurrency-safe — and owns one event loop via ``asyncio.run``. The pool
    is acquired (built lazily on first query) but **not** closed here; the manager owns lifecycle.
    """
    init_db()
    run_id = _create_agent_run(query_record_id)
    initial: AgentState = {
        "run_id": run_id,
        "query_record_id": query_record_id,
        "session_id": session_id,
        "question": question,
        "error": None,
    }
    manager = get_manager()
    log.info("pipeline.start", run_id=run_id, query_record_id=query_record_id, session_id=session_id)
    with manager.session_lock(session_id):  # serialize queries within a session
        final = asyncio.run(_run_async(initial, session_id, run_id))
    log.info("pipeline.complete", run_id=run_id, status="done")
    return final


async def _run_async(initial: AgentState, session_id: str, run_id: str) -> AgentState:
    """Acquire the session pool (lazy build), then invoke the graph."""
    try:
        await get_manager().acquire(session_id)
    except Exception as exc:
        message = f"Failed to load data: {exc}"
        log.error("pipeline.acquire_failed", run_id=run_id, error=str(exc))
        mark_failed(initial, message)
        return {**initial, "error": message}
    return await agent_graph.ainvoke(initial)


def _create_agent_run(query_record_id: str) -> str:
    """Insert a new agent run row for a query record and return its id."""
    with create_db_session() as db:
        run = AgentRunRow(query_record_id=query_record_id)
        db.add(run)
        db.flush()
        return run.id
