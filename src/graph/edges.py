from graph.state import AgentState

# Default bound on the retry-on-SQL-error loop (agent.md).
MAX_SQL_RETRIES = 3


def after_generate_sql(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_sql"


def after_execute(state: AgentState) -> str:
    """Retry-on-SQL-error routing.

    - sql_error set AND attempts < max  -> generate_sql (retry, error fed back)
    - sql_error set AND attempts >= max  -> handle_error (exhausted)
    - no sql_error                       -> answer
    """
    if state.get("sql_error"):
        if state.get("sql_attempts", 0) < MAX_SQL_RETRIES:
            return "generate_sql"
        return "handle_error"
    return "answer"


def after_answer(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    # On success, enrich with suggested follow-ups before finalizing.
    return "suggest_followups"
