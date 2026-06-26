from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    profile_csv,
    generate_code,
    execute_code,
    explain_result,
    finalize,
    handle_error,
)
from graph.edges import after_profile, after_generate, after_execute, after_explain


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("profile_csv", profile_csv)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("explain_result", explain_result)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("profile_csv")
    g.add_conditional_edges(
        "profile_csv",
        after_profile,
        {"generate_code": "generate_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "generate_code",
        after_generate,
        {"execute_code": "execute_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code",
        after_execute,
        {
            "explain_result": "explain_result",
            "generate_code": "generate_code",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "explain_result",
        after_explain,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
