"""Conditional-edge routing functions for the analyst graph.

Each returns the name of the next node. Phase 1: any error routes to
``handle_error``. The retry branch out of ``execute_code`` is wired in the graph
assembly but is never taken in Phase 1 (retry is Phase 2).
"""

from graph.state import AgentState


def after_profile(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "generate_code"


def after_generate(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_code"


def after_execute(state: AgentState) -> str:
    # Phase 1: no retry. On error → handle_error. The "generate_code" retry
    # target exists in the edge mapping but is never returned here yet.
    if state.get("error"):
        return "handle_error"
    return "explain_result"


def after_explain(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
