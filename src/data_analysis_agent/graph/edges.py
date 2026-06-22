from data_analysis_agent.graph.state import AgentState

_FINAL_PREFIX = "FINAL ANSWER:"


def route_after_load(state: AgentState) -> str:
    """Route to error handling if loading failed, otherwise to planning."""
    return "handle_error" if state.get("error") else "plan_action"


def route_after_plan(state: AgentState) -> str:
    """Route to error, finalize (on FINAL ANSWER), or execution of the next call."""
    if state.get("error"):
        return "handle_error"
    if state.get("llm_response", "").upper().startswith(_FINAL_PREFIX):
        return "finalize"
    return "execute_action"


def route_after_execute(state: AgentState) -> str:
    """Route to error handling if the action failed, otherwise back to planning."""
    return "handle_error" if state.get("error") else "plan_action"


def route_after_finalize(state: AgentState) -> str:
    """Route to error handling if persistence failed, otherwise to END."""
    return "handle_error" if state.get("error") else "end"
