from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                      # set by runner before invoke
    dataset_id: str                  # which dataset to query
    dataset_path: str                # local DuckDB file path (set by runner)
    schema: list[dict]               # [{name, type}, ...] — sent to LLM
    question: str                    # the user's plain-English question (input)

    # Pipeline data (populated by nodes)
    sql: str | None                  # DuckDB SQL from generate_sql
    sql_error: str | None            # last DuckDB error (fed back on retry)
    sql_attempts: int                # retry counter (starts 0)
    result_rows: list[dict] | None   # aggregate result from execute_sql (capped)

    # Output
    answer_text: str | None          # plain-English answer from answer node
    output_text: str | None          # serialized answer+SQL+result for the Run row
    flagged: bool                    # best-guess badge

    # Phase 2 enrichment (all derived from aggregate result only — no raw rows)
    chart: dict | None               # chart spec from result shape (or None)
    summary_table: dict | None       # formatted {columns, rows} table (or None)
    followups: list[str] | None      # 2-3 suggested follow-up questions (or None)

    # Control
    status: str                      # "completed" | "failed"
    error: str | None                # fatal error -> handle_error
