import structlog

from data_analysis_agent.graph.agent import agent_graph
from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.db.session import create_db_session, init_db
from data_analysis_agent.db.models import QueryRecordRow, AgentRunRow

log = structlog.get_logger()


def run_pipeline(
    query_record_id: str,
    session_id: str,
    question: str,
) -> AgentState:
    """Create an agent run and execute the ReAct graph to completion, returning the final state."""
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
    final = agent_graph.invoke(initial)
    log.info("pipeline.complete", run_id=run_id, status="done")
    return final


def _create_agent_run(query_record_id: str) -> str:
    """Insert a new agent run row for a query record and return its id."""
    with create_db_session() as db:
        run = AgentRunRow(query_record_id=query_record_id)
        db.add(run)
        db.flush()
        return run.id
