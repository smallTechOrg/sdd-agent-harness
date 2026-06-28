from typing import TypedDict, Any


class ExecutionStep(TypedDict):
    iteration: int
    code: str
    stdout: str
    stderr: str
    success: bool
    elapsed_s: float


class ExecutionResult(TypedDict):
    stdout: str
    stderr: str
    success: bool
    elapsed_s: float
    complete: bool      # set by inspect_result
    explanation: str    # set by inspect_result


class FileProfile(TypedDict):
    columns: list[dict]
    row_count: int
    column_count: int
    file_size_bytes: int
    profiled_at: str


class AnalysisState(TypedDict, total=False):
    # Identity
    query_run_id: str
    # Input
    question: str
    file_ids: list[str]
    session_id: str | None
    # Data context
    profiles: list[FileProfile]
    data_paths: list[str]
    # Reasoning loop
    plan: str
    iteration: int
    max_iterations: int
    execution_history: list[ExecutionStep]
    last_execution_result: ExecutionResult | None
    last_execution_error: str | None
    # Clarification branch
    needs_clarification: bool
    clarification_question: str | None
    # Output
    answer_text: str | None
    plotly_chart: dict | None
    followup_suggestions: list[str]
    # Observability
    input_tokens: int
    output_tokens: int
    cost_usd: float
    # Control
    error: str | None
    checkpoint: str | None
    # SSE callback (not serialized — injected at runtime)
    _sse_emit: Any  # callable(event_type, data) | None
    # Internal stash for generated code between plan and execute nodes
    _generated_code: str | None
