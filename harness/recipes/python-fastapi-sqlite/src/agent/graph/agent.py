from langgraph.graph import StateGraph, END

from agent.graph.state import AgentState
from agent.graph.nodes import transform_text, handle_error, finalize
from agent.graph.edges import after_transform


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("transform_text", transform_text)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.set_entry_point("transform_text")
    g.add_conditional_edges(
        "transform_text",
        after_transform,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
