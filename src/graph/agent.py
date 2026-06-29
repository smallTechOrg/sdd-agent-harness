from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    generate_sql,
    execute_sql,
    answer,
    suggest_followups,
    finalize,
    handle_error,
)
from graph.edges import after_generate_sql, after_execute, after_answer


def _build_graph():
    g = StateGraph(AgentState)

    g.add_node("generate_sql", generate_sql)
    g.add_node("execute_sql", execute_sql)
    g.add_node("answer", answer)
    g.add_node("suggest_followups", suggest_followups)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("generate_sql")

    g.add_conditional_edges(
        "generate_sql",
        after_generate_sql,
        {"handle_error": "handle_error", "execute_sql": "execute_sql"},
    )
    g.add_conditional_edges(
        "execute_sql",
        after_execute,
        {
            "generate_sql": "generate_sql",
            "handle_error": "handle_error",
            "answer": "answer",
        },
    )
    g.add_conditional_edges(
        "answer",
        after_answer,
        {"handle_error": "handle_error", "suggest_followups": "suggest_followups"},
    )
    # suggest_followups is non-fatal — it always proceeds to finalize.
    g.add_edge("suggest_followups", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()


agentic_ai = _build_graph()
