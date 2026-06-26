from graph.state import AgentState


def route_or_error(state: AgentState, next_node: str) -> str:
    if state.get("error"):
        return "handle_error"
    return next_node
