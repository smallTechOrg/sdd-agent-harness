from graph.state import AgentState


def after_transform(state: AgentState) -> str:
    # Kept for the bare transform_text capability slot.
    if state.get("error"):
        return "handle_error"
    return "finalize"


def after_react(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    # More tool calls queued and budget holds → loop; else we have an answer.
    if state.get("messages") and state["messages"][-1].get("role") == "user":
        # last turn is tool results → the model must observe them
        return "react"
    return "guard_output"
