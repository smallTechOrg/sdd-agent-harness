from langgraph.graph import StateGraph, END

from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.graph.nodes import plan_action, execute_action, finalize, handle_error
from data_analysis_agent.graph.edges import (
    route_after_plan, route_after_execute, route_after_finalize,
)


def build_graph() -> StateGraph:
    """Build the (uncompiled) ReAct agent graph.

    The per-query loop is plan → execute → finalize/handle_error; the session's MCP pool is
    acquired by ``run_pipeline`` before the graph runs. Returned uncompiled so the runner can
    ``compile(checkpointer=...)`` per query (binding durable memory to ``thread_id``).
    """
    g = StateGraph(AgentState)
    g.add_node("plan_action", plan_action)        # all async def
    g.add_node("execute_action", execute_action)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)
    g.set_entry_point("plan_action")
    g.add_conditional_edges(
        "plan_action", route_after_plan,
        {"execute_action": "execute_action", "finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_action", route_after_execute,
        {"plan_action": "plan_action", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "finalize", route_after_finalize,
        {"end": END, "handle_error": "handle_error"},
    )
    g.add_edge("handle_error", END)
    return g
