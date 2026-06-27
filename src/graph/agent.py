from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import plan_sql, execute_sql, finalize, handle_error
from graph.edges import after_plan_sql, after_execute_sql


def _build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("plan_sql", plan_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("finalize", finalize)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("plan_sql")

    graph.add_conditional_edges(
        "plan_sql",
        after_plan_sql,
        {"handle_error": "handle_error", "execute_sql": "execute_sql"},
    )
    graph.add_conditional_edges(
        "execute_sql",
        after_execute_sql,
        {"handle_error": "handle_error", "finalize": "finalize"},
    )

    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


agentic_ai = _build_graph()
