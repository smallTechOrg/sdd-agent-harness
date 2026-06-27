from graph.state import AgentState


def after_plan_sql(state: AgentState) -> str:
    """Route plan_sql -> handle_error on failure, else execute_sql."""
    return "handle_error" if state.get("error") else "execute_sql"


def after_execute_sql(state: AgentState) -> str:
    """Route execute_sql -> handle_error on failure, else finalize."""
    return "handle_error" if state.get("error") else "finalize"
