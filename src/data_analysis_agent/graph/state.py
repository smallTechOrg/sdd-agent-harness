from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    query_record_id: str
    session_id: str          # also the checkpointer thread_id
    question: str

    # Durable per-session memory: prior {"question","answer"} turns, restored across queries by
    # the SqliteSaver checkpointer (keyed by thread_id=session_id). This is a plain "last-value"
    # channel — `finalize` writes the FULL updated list (read restored + append). A reducer
    # (operator.add) is intentionally NOT used: on checkpoint resume LangGraph replays writes,
    # which double-appends with a reducer; an idempotent overwrite is correct under replay.
    conversation: list[dict]

    # Tools + schema are read from the SessionPoolManager (by session_id), not stored here.
    # The MCP servers + DuckDB connections live in that manager, never in state.

    # ReAct loop state (per-query scratch — reset via the ainvoke input each query)
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
