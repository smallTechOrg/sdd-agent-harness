from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                  # set at initialisation by run_agent

    # Input
    input_text: str              # the NL question (existing key, reused)
    dataset_id: str | None       # active dataset; None -> seeded "sales"

    # Pipeline data
    schema: list[dict]           # [{"column": str, "type": str}] from introspect
    sample_rows: list[list]      # <= N sample rows for LLM context
    sql: str                     # SELECT produced by plan_sql (after guard)
    chart_spec: dict             # {"chart_type","x","y":[...]}

    # Output
    columns: list[str]           # from execute_sql
    rows: list[list]             # from execute_sql (bounded)
    output_text: str             # JSON-serialized payload written by finalize

    # Control
    status: str                  # "completed" | "failed"
    error: str | None            # set by any node on fatal failure
