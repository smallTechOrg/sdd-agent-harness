from graph.state import AgentState


def after_analyze(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
