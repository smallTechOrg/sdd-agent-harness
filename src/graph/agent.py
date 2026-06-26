from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    schema_introspection,
    sql_generation,
    sql_execution,
    chart_selection,
    insight_generation,
    handle_error,
    finalize,
)
from graph.edges import route_or_error


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("schema_introspection", schema_introspection)
    g.add_node("sql_generation", sql_generation)
    g.add_node("sql_execution", sql_execution)
    g.add_node("chart_selection", chart_selection)
    g.add_node("insight_generation", insight_generation)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("schema_introspection")

    g.add_conditional_edges(
        "schema_introspection",
        lambda s: route_or_error(s, "sql_generation"),
        {"sql_generation": "sql_generation", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "sql_generation",
        lambda s: route_or_error(s, "sql_execution"),
        {"sql_execution": "sql_execution", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "sql_execution",
        lambda s: route_or_error(s, "chart_selection"),
        {"chart_selection": "chart_selection", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "chart_selection",
        lambda s: route_or_error(s, "insight_generation"),
        {"insight_generation": "insight_generation", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "insight_generation",
        lambda s: route_or_error(s, "finalize"),
        {"finalize": "finalize", "handle_error": "handle_error"},
    )

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
