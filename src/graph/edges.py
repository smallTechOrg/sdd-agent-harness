from graph.state import AnalysisState


def after_generate_sql(state: AnalysisState) -> str:
    return "handle_error" if state.get("error") else "execute_sql"


def after_execute_sql(state: AnalysisState) -> str:
    return "handle_error" if state.get("error") else "generate_insights"


def after_generate_insights(state: AnalysisState) -> str:
    return "handle_error" if state.get("error") else "generate_charts"


# generate_charts always goes to finalize — no conditional edge needed (use add_edge)
# Kept here for potential Phase 3 use
def after_generate_charts(state: AnalysisState) -> str:
    return "finalize"


# Backward compatibility alias
def after_transform(state: AnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
