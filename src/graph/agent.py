from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    guard_input, load_memory, react, guard_output, write_memory,
    transform_text, handle_error, finalize,
)
from graph.edges import after_react


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Seam nodes + the active capability node + the bare 0-tool slot.
    g.add_node("guard_input", guard_input)
    g.add_node("load_memory", load_memory)
    g.add_node("react", react)
    g.add_node("guard_output", guard_output)
    g.add_node("write_memory", write_memory)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)
    g.add_node("transform_text", transform_text)   # wired + tested, off the composed path

    g.set_entry_point("guard_input")

    g.add_conditional_edges(
        "guard_input",
        lambda s: "handle_error" if s.get("error") else "load_memory",
        {"handle_error": "handle_error", "load_memory": "load_memory"},
    )
    g.add_edge("load_memory", "react")
    g.add_conditional_edges(
        "react",
        after_react,
        {"react": "react", "handle_error": "handle_error", "guard_output": "guard_output"},
    )
    g.add_conditional_edges(
        "guard_output",
        lambda s: "handle_error" if s.get("error") else "write_memory",
        {"handle_error": "handle_error", "write_memory": "write_memory"},
    )
    g.add_edge("write_memory", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
