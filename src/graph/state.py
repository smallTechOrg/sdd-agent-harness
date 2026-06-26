from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    run_id: str           # UUID of the QueryRun DB record
    session_id: str       # UUID of the UploadSession
    table_name: str       # SQLite dynamic table name e.g. "sales_data_a3f7b2c1"
    question: str         # Natural-language question from the user
    schema: list[dict]    # [{"name": "col", "type": "TEXT"}, ...]
    sql: str              # SELECT query from sql_generation
    rows: list[dict]      # Query result rows from sql_execution
    chart_spec: dict      # Recharts-compatible JSON spec
    insight: str          # Plain-English insight paragraph
    error: str | None     # Set by any node on fatal failure
    status: str           # "pending" | "completed" | "failed"
