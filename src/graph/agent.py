"""Graph assembly for the DataChat plan-execute agent.

Wires the nodes from ``graph/nodes.py`` into the topology specified in
``spec/agent.md`` -> "Graph Assembly":

    START -> profile_context -> plan -> generate_code -> execute_local
          -> synthesize -> finalize -> END

with error edges from plan / generate_code / synthesize to ``handle_error`` and a
self-correction edge from ``execute_local`` back to ``generate_code`` (retry once)
before falling through to ``handle_error``.

The compiled graph is exported as ``agentic_ai`` (kept name from the skeleton).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from graph.edges import route_after_execute
from graph.nodes import (
    node_execute_local,
    node_finalize,
    node_generate_code,
    node_handle_error,
    node_plan,
    node_profile_context,
    node_synthesize,
)
from graph.state import AgentState


def _build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("profile_context", node_profile_context)
    graph.add_node("plan", node_plan)
    graph.add_node("generate_code", node_generate_code)
    graph.add_node("execute_local", node_execute_local)
    graph.add_node("synthesize", node_synthesize)
    graph.add_node("finalize", node_finalize)
    graph.add_node("handle_error", node_handle_error)

    graph.set_entry_point("profile_context")
    graph.add_edge("profile_context", "plan")

    graph.add_conditional_edges(
        "plan",
        lambda s: "handle_error" if s.get("error") else "generate_code",
        {"handle_error": "handle_error", "generate_code": "generate_code"},
    )
    graph.add_conditional_edges(
        "generate_code",
        lambda s: "handle_error" if s.get("error") else "execute_local",
        {"handle_error": "handle_error", "execute_local": "execute_local"},
    )
    graph.add_conditional_edges(
        "execute_local",
        route_after_execute,  # exec_error+retries->generate_code | exec_error->handle_error | ok->synthesize
        {
            "generate_code": "generate_code",
            "handle_error": "handle_error",
            "synthesize": "synthesize",
        },
    )
    graph.add_conditional_edges(
        "synthesize",
        lambda s: "handle_error" if s.get("error") else "finalize",
        {"handle_error": "handle_error", "finalize": "finalize"},
    )

    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


agentic_ai = _build_graph()
