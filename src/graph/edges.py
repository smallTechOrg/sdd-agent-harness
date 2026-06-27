from graph.state import AgentState


def after_profile(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "plan_compute"


def after_plan(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_local"


def after_execute(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "phrase_answer"


def after_phrase(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
