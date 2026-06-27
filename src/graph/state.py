from typing import TypedDict


class AgentState(TypedDict, total=False):
    """State for the code-interpreter analysis loop (see spec/agent.md).

    The full dataframe is never stored here and never sent to the LLM; only
    ``schema_summary`` leaves the machine. ``execute_code`` loads the full frame
    from ``dataframe_path`` at execution time.
    """

    run_id: str
    dataset_id: str
    question: str
    schema_summary: str
    dataframe_path: str
    generated_code: str | None
    execution_result: str | None
    execution_steps: str | None
    execution_error: str | None
    attempts: int
    max_attempts: int
    answer: str | None
    error: str | None
    status: str
