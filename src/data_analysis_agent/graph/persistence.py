from __future__ import annotations

import json

from data_analysis_agent.db.models import AgentRunRow, QueryRecordRow
from data_analysis_agent.db.session import create_db_session
from data_analysis_agent.graph.state import AgentState


def mark_completed(state: AgentState) -> None:
    """Persist a successful run: answer, usage stats, and the full tool trace.

    Args:
        state: The final agent state carrying the answer and usage counters.
    """
    with create_db_session() as db:
        query_record = db.get(QueryRecordRow, state["query_record_id"])
        if query_record:
            _apply_completion(query_record, state)
        run = db.get(AgentRunRow, state["run_id"])
        if run:
            run.status = "completed"


def mark_failed(state: AgentState, error_message: str) -> None:
    """Persist a failure status and message to the query record and the run.

    Args:
        state: The agent state identifying the query record and run.
        error_message: The human-readable failure detail to store.
    """
    with create_db_session() as db:
        query_record = db.get(QueryRecordRow, state.get("query_record_id", ""))
        if query_record:
            query_record.status = "failed"
            query_record.error_message = error_message
        run = db.get(AgentRunRow, state.get("run_id", ""))
        if run:
            run.status = "failed"
            run.error_message = error_message


def _apply_completion(query_record: QueryRecordRow, state: AgentState) -> None:
    """Copy the answer, usage stats, and history from state onto a query record."""
    query_record.answer = state.get("answer", "")
    query_record.status = "completed"
    query_record.iteration_count = state.get("iteration_count", 0)
    query_record.query_history_json = json.dumps(state.get("action_history", []))
    query_record.input_tokens = state.get("input_tokens", 0)
    query_record.output_tokens = state.get("output_tokens", 0)
    query_record.total_tokens = state.get("total_tokens", 0)
    query_record.estimated_cost_usd = state.get("estimated_cost_usd")
    query_record.api_request_count = state.get("api_request_count", 1)
