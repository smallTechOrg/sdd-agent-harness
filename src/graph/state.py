from typing import TypedDict


class AgentState(TypedDict, total=False):
    """Run state for the data-analyst pipeline.

    profile_schema -> generate_sql -> execute_sql -> narrate -> finalize
    (any node may set ``error`` and route to handle_error).
    """

    # Identity (set by runner)
    run_id: str
    session_id: str
    dataset_id: str

    # Input (set by runner)
    nl_question: str
    duckdb_path: str
    max_sample_rows: int
    table_name: str

    # Pipeline data (populated progressively)
    schema_context: dict
    generated_sql: str
    result_columns: list[str]
    result_rows: list[list]
    row_count: int
    duration_ms: int

    # Output
    narrative: str
    status: str

    # Control
    error: str | None
