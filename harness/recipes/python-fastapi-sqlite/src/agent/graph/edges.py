from agent.graph.state import AgentState


def after_transform(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
