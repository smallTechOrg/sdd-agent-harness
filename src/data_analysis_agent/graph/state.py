from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    query_record_id: str
    session_id: str
    question: str

    # MCP tools, aggregated from list_tools() across all source servers by load_data.
    # Flat — MCP has no nested capabilities. (Sessions/servers live in mcp_pool, not here.)
    tools: list[dict]  # [{"name", "table_name", "description", "parameter_schema"}]

    # Schema info (table.column across all attached sources)
    column_names: list[str]
    row_count: int

    # ReAct loop state
    action_history: list[dict]  # [{"tool", "arguments", "result", "is_error"}]
    iteration_count: int
    llm_response: str  # raw LLM output from last plan_action call

    # Final output
    answer: str

    # Usage tracking
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    api_request_count: int

    # Control
    error: str | None
