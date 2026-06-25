import asyncio

import structlog
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import AgentRunRow
from data_analysis_agent.db.session import create_db_session, init_db
from data_analysis_agent.graph.agent import build_graph
from data_analysis_agent.graph.persistence import mark_failed
from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.tools.mcp.pool import get_manager

log = structlog.get_logger()


def run_pipeline(
    query_record_id: str,
    session_id: str,
    question: str,
) -> AgentState:
    """Run one query against a session's (reused) MCP pool, with durable memory.

    Stays synchronous; holds the per-session lock for the whole query (the session's DuckDB
    connection is not concurrency-safe) and owns one event loop via ``asyncio.run``. Memory is
    a LangGraph ``AsyncSqliteSaver`` checkpoint keyed by ``thread_id = session_id`` — opened
    inside the run and durable across these per-query savers because it is file-backed.
    """
    init_db()
    run_id = _create_agent_run(query_record_id)
    manager = get_manager()
    log.info("pipeline.start", run_id=run_id, query_record_id=query_record_id, session_id=session_id)
    with manager.session_lock(session_id):  # serialize queries within a session
        final = asyncio.run(_run_async(query_record_id, session_id, run_id, question))
    log.info("pipeline.complete", run_id=run_id, status="done")
    return final


async def _run_async(query_record_id: str, session_id: str, run_id: str, question: str) -> AgentState:
    """Acquire the session pool, then invoke the checkpointed graph for this session thread."""
    initial = _fresh_input(run_id, query_record_id, session_id, question)
    try:
        await get_manager().acquire(session_id)
    except Exception as exc:
        message = f"Failed to load data: {exc}"
        log.error("pipeline.acquire_failed", run_id=run_id, error=str(exc))
        mark_failed(initial, message)
        return {**initial, "error": message}

    async with AsyncSqliteSaver.from_conn_string(get_settings().checkpoint_db) as saver:
        await saver.setup()
        graph = build_graph().compile(checkpointer=saver)
        return await graph.ainvoke(initial, config={"configurable": {"thread_id": session_id}})


def _fresh_input(run_id: str, query_record_id: str, session_id: str, question: str) -> AgentState:
    """Per-query input that resets all scratch state.

    ``conversation`` is intentionally omitted so the checkpointer's restored memory is kept
    (and this turn appended by ``finalize``); every other field is reset to a clean value so
    the previous query's scratch never bleeds into this run.
    """
    return {
        "run_id": run_id,
        "query_record_id": query_record_id,
        "session_id": session_id,
        "question": question,
        "action_history": [],
        "iteration_count": 0,
        "llm_response": "",
        "answer": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "api_request_count": 0,
        "error": None,
    }


def _create_agent_run(query_record_id: str) -> str:
    """Insert a new agent run row for a query record and return its id."""
    with create_db_session() as db:
        run = AgentRunRow(query_record_id=query_record_id)
        db.add(run)
        db.flush()
        return run.id
