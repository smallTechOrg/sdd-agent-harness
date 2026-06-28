from langgraph.graph import StateGraph, END

from data_analysis.graph.state import AnalysisState
from data_analysis.graph.nodes import (
    node_profile_data,
    node_plan_steps,
    node_execute_code,
    node_inspect_result,
    node_synthesize_answer,
    node_finalize,
    node_handle_error,
    node_stream_clarification,
)
from data_analysis.graph.edges import (
    edge_after_profile,
    edge_after_plan,
    edge_after_execute,
    edge_after_inspect,
    edge_after_synthesize,
)


def build_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("profile_data", node_profile_data)
    graph.add_node("plan_steps", node_plan_steps)
    graph.add_node("execute_code", node_execute_code)
    graph.add_node("inspect_result", node_inspect_result)
    graph.add_node("synthesize_answer", node_synthesize_answer)
    graph.add_node("finalize", node_finalize)
    graph.add_node("handle_error", node_handle_error)
    graph.add_node("stream_clarification", node_stream_clarification)

    graph.set_entry_point("profile_data")
    graph.add_conditional_edges("profile_data", edge_after_profile)
    graph.add_conditional_edges("plan_steps", edge_after_plan)
    graph.add_conditional_edges("execute_code", edge_after_execute)
    graph.add_conditional_edges("inspect_result", edge_after_inspect)
    graph.add_conditional_edges("synthesize_answer", edge_after_synthesize)
    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)
    graph.add_edge("stream_clarification", END)

    return graph.compile()


compiled_graph = build_graph()
