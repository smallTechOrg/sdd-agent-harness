from langgraph.graph import StateGraph, END

from data_analysis_agent.graph.state import AgentState
from data_analysis_agent.graph.nodes import load_data, plan_action, execute_action, finalize, handle_error
from data_analysis_agent.graph.edges import (
    route_after_load, route_after_plan, route_after_execute, route_after_finalize,
)


def _build_graph() -> StateGraph:
    """Build and compile the ReAct agent graph from its nodes and edges."""
    g = StateGraph(AgentState)
    _add_nodes(g)
    g.set_entry_point("load_data")
    _add_edges(g)
    return g.compile()


def _add_nodes(g: StateGraph) -> None:
    """Register the five ReAct nodes on the graph."""
    g.add_node("load_data", load_data)
    g.add_node("plan_action", plan_action)
    g.add_node("execute_action", execute_action)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)


def _add_edges(g: StateGraph) -> None:
    """Wire the conditional routing between nodes, ending at ``handle_error``."""
    g.add_conditional_edges(
        "load_data", route_after_load,
        {"plan_action": "plan_action", "handle_error": "handle_error"},
    )
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


agent_graph = _build_graph()
