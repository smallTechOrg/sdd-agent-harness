from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    profile_data, plan_compute, execute_local,
    phrase_answer, finalize, handle_error,
)
from graph.edges import (
    after_profile, after_plan, after_execute, after_phrase,
)


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("profile_data", profile_data)
    g.add_node("plan_compute", plan_compute)
    g.add_node("execute_local", execute_local)
    g.add_node("phrase_answer", phrase_answer)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("profile_data")
    g.add_conditional_edges("profile_data", after_profile,
        {"plan_compute": "plan_compute", "handle_error": "handle_error"})
    g.add_conditional_edges("plan_compute", after_plan,
        {"execute_local": "execute_local", "handle_error": "handle_error"})
    g.add_conditional_edges("execute_local", after_execute,
        {"phrase_answer": "phrase_answer", "handle_error": "handle_error"})
    g.add_conditional_edges("phrase_answer", after_phrase,
        {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
