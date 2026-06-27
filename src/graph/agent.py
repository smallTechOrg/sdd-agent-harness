from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import analyze_data, handle_error, finalize
from graph.edges import after_analyze


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("analyze_data", analyze_data)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.set_entry_point("analyze_data")
    g.add_conditional_edges(
        "analyze_data",
        after_analyze,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
