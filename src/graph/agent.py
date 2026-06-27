from langgraph.graph import StateGraph, END

from graph.state import AnalysisState
from graph.nodes import (
    generate_sql, execute_sql,
    generate_insights, generate_charts,
    handle_error, finalize,
)
from graph.edges import (
    after_generate_sql, after_execute_sql, after_generate_insights,
)


def _build_graph() -> StateGraph:
    g = StateGraph(AnalysisState)

    g.add_node("generate_sql", generate_sql)
    g.add_node("execute_sql", execute_sql)
    g.add_node("generate_insights", generate_insights)
    g.add_node("generate_charts", generate_charts)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_sql")

    g.add_conditional_edges(
        "generate_sql",
        after_generate_sql,
        {"execute_sql": "execute_sql", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_sql",
        after_execute_sql,
        {"generate_insights": "generate_insights", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "generate_insights",
        after_generate_insights,
        {"generate_charts": "generate_charts", "handle_error": "handle_error"},
    )
    # generate_charts always continues — it degrades gracefully (chart_specs=[]) rather than aborting
    g.add_edge("generate_charts", "finalize")

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
