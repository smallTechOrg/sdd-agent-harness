"""
Runner for the data-analysis pipeline.

The primary entry point is the query endpoint (src/api/query.py), which
calls agentic_ai.invoke() directly. This module exposes run_query() as a
convenience wrapper for scripts and future CLI use.
"""
from graph.agent import agentic_ai
from graph.state import AgentState


def run_query(
    session_id: str,
    table_name: str,
    question: str,
    run_id: str,
) -> AgentState:
    """Invoke the 5-node pipeline and return the final state."""
    initial: AgentState = {
        "run_id": run_id,
        "session_id": session_id,
        "table_name": table_name,
        "question": question,
    }
    return agentic_ai.invoke(initial)
