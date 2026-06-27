"""Conditional-edge routers for the DataChat graph.

Each router sends the turn to ``handle_error`` when a node set ``state["error"]``,
otherwise to the next node in the pipeline (per the topology in spec/agent.md).
"""
from graph.state import AgentState


def after_plan(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "run_local_aggregation"


def after_aggregate(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "compose_answer_and_pick_chart"


def after_compose(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
