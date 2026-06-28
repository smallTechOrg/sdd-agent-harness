"""Pandora analysis graph assembly (see spec/agent.md).

START → generate_code → validate_code
  validate_code ─ valid ──▶ execute_code      └ invalid ─▶ (retry?) generate_code | handle_error
  execute_code  ─ ok ─────▶ summarise         └ error  ─▶ (retry?) generate_code | handle_error
  summarise     ─ ok ─────▶ finalize          └ error  ─▶ handle_error
  finalize → END · handle_error → END

Compiled once at import; the import requires no env vars or API keys.
"""

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    generate_code,
    validate_code,
    execute_code,
    summarise,
    handle_error,
    finalize,
)
from graph.edges import after_validate, after_execute, after_summarise


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("generate_code", generate_code)
    g.add_node("validate_code", validate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("summarise", summarise)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_code")
    g.add_edge("generate_code", "validate_code")
    g.add_conditional_edges(
        "validate_code",
        after_validate,
        {
            "execute_code": "execute_code",
            "generate_code": "generate_code",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "execute_code",
        after_execute,
        {
            "summarise": "summarise",
            "generate_code": "generate_code",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "summarise",
        after_summarise,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
