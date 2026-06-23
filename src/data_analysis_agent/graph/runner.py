import asyncio

import structlog

from data_analysis_agent.db.models import AgentRunRow
from data_analysis_agent.db.session import create_db_session, init_db
from data_analysis_agent.graph.agent import agent_graph
from data_analysis_agent.graph.mcp_pool import close_pool
from data_analysis_agent.graph.state import AgentState

log = structlog.get_logger()


def run_pipeline(
    query_record_id: str,
    session_id: str,
    question: str,
) -> AgentState:
    """Create an agent run and execute the async ReAct graph to completion.

    Stays synchronous (so the HTTP handler's background thread and the integration
    tests call it unchanged) but owns a fresh event loop for the whole run via
    ``asyncio.run`` — all MCP work then happens on one loop.

    Returns:
        The final :class:`AgentState`.
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
    log.info("pipeline.start", run_id=run_id, query_record_id=query_record_id)
    final = asyncio.run(_run_async(initial, run_id))
    log.info("pipeline.complete", run_id=run_id, status="done")
    return final


async def _run_async(initial: AgentState, run_id: str) -> AgentState:
    """Invoke the graph and guarantee the run's MCP pool is torn down."""
    try:
        return await agent_graph.ainvoke(initial)
    finally:
        await close_pool(run_id)


def _create_agent_run(query_record_id: str) -> str:
    """Insert a new agent run row for a query record and return its id."""
    with create_db_session() as db:
        run = AgentRunRow(query_record_id=query_record_id)
        db.add(run)
        db.flush()
        return run.id
