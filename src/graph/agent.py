from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    profile_schema,
    generate_sql,
    execute_sql,
    narrate,
    finalize,
    handle_error,
)
from graph.edges import _route


def _build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("profile_schema", profile_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("narrate", narrate)
    graph.add_node("finalize", finalize)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("profile_schema")

    graph.add_conditional_edges(
        "profile_schema",
        _route("generate_sql"),
        {"generate_sql": "generate_sql", "handle_error": "handle_error"},
    )
    graph.add_conditional_edges(
        "generate_sql",
        _route("execute_sql"),
        {"execute_sql": "execute_sql", "handle_error": "handle_error"},
    )
    graph.add_conditional_edges(
        "execute_sql",
        _route("narrate"),
        {"narrate": "narrate", "handle_error": "handle_error"},
    )
    graph.add_conditional_edges(
        "narrate",
        _route("finalize"),
        {"finalize": "finalize", "handle_error": "handle_error"},
    )

    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


agentic_ai = _build_graph()
