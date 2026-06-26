from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str

    # Input (from the trigger) — local only, csv_text/df never sent to the LLM
    csv_text: str
    question: str
    mode: str                   # "pandas" (default) | "sql" — determines code generation and execution path

    # Full DataFrame — held in-process for local execution ONLY. Never serialized
    # into any LLM prompt.
    df: Any

    # Pipeline data (populated progressively by the nodes)
    schema: list[dict]          # [{name, dtype}] — profile_csv (LLM-visible)
    sample_rows: list[dict]     # capped sample rows — profile_csv (LLM-visible)
    row_count: int              # full row count — profile_csv
    generated_code: str         # pandas snippet or SQL query — generate_code
    result_table: dict | None   # {columns, rows} — execute_code
    result_scalar: Any | None   # scalar result when applicable — execute_code
    truncated: bool             # result-table truncated flag — execute_code

    # Output
    answer: str | None          # short answer line — explain_result
    explanation: str | None     # plain-English explanation — explain_result
    status: str                 # "completed" | "failed" — finalize/handle_error

    # Control
    error: str | None           # set by any node on fatal failure
    retry_count: int            # bounded retries of generate_code (Phase 2)
