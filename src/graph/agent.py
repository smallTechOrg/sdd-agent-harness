from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import generate_code, execute_code, summarize, handle_error
from graph.edges import route_after_execute


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("summarize", summarize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("generate_code")
    g.add_edge("generate_code", "execute_code")
    g.add_conditional_edges(
        "execute_code",
        route_after_execute,
        {
            "summarize": "summarize",
            "generate_code": "generate_code",
            "handle_error": "handle_error",
        },
    )
    g.add_edge("summarize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
