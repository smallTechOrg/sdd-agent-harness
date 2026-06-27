from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    plan_aggregation,
    run_local_aggregation,
    compose_answer_and_pick_chart,
    finalize,
    handle_error,
)
from graph.edges import after_plan, after_aggregate, after_compose


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan_aggregation", plan_aggregation)
    g.add_node("run_local_aggregation", run_local_aggregation)  # NO LLM — privacy firewall
    g.add_node("compose_answer_and_pick_chart", compose_answer_and_pick_chart)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("plan_aggregation")
    g.add_conditional_edges(
        "plan_aggregation",
        after_plan,
        {"run_local_aggregation": "run_local_aggregation", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "run_local_aggregation",
        after_aggregate,
        {"compose_answer_and_pick_chart": "compose_answer_and_pick_chart", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "compose_answer_and_pick_chart",
        after_compose,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
