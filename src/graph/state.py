from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    error: str | None
    status: str | None     # "completed" | "failed" — set by finalize / handle_error
    # Analysis fields
    dataset_id: str | None
    question: str | None
    chart_type: str | None     # "bar" | "line" | "scatter"
    labels: list | None        # Real labels from pandas execution
    values: list | None        # Real values from pandas execution
    summary: str | None        # Written summary from Gemini
