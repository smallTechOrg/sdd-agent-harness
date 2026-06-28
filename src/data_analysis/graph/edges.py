from langgraph.graph import END

from data_analysis.graph.state import AnalysisState


def edge_after_profile(state: AnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    return "plan_steps"


def edge_after_plan(state: AnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("needs_clarification") and state.get("iteration", 0) == 0:
        return "stream_clarification"
    return "execute_code"


def edge_after_execute(state: AnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    return "inspect_result"


def edge_after_inspect(state: AnalysisState) -> str:
    """Decide whether to loop (plan again) or synthesize."""
    if state.get("error"):
        return "handle_error"
    last_result = state.get("last_execution_result") or {}
    complete = last_result.get("complete", False)
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", 5)
    if complete or iteration >= max_iter:
        return "synthesize_answer"
    return "plan_steps"


def edge_after_synthesize(state: AnalysisState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
