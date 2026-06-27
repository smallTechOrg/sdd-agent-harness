from graph.state import AgentState


def route_after_execute(state: AgentState) -> str:
    """Route after execute_code (see spec/agent.md).

    - no error            → summarize (success finalizer)
    - error, retries left → generate_code (feed the error back, regenerate)
    - error, exhausted    → handle_error (terminal failure)
    """
    if not state.get("execution_error"):
        return "summarize"
    if state.get("attempts", 0) < state.get("max_attempts", 3):
        return "generate_code"
    return "handle_error"
