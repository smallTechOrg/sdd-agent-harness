from typing import TypedDict


class NodeTrace(TypedDict):
    node: str
    duration_ms: float


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str
    conversation_id: str                 # keys session memory

    # Input
    input_text: str

    # ReAct loop
    messages: list[dict]                 # provider-shaped running history
    iterations: int                      # THE loop counter (react owns it; budget reads it)

    # Memory
    memory_context: str                  # session transcript, fenced as untrusted

    # Output
    output_text: str

    # Observability — populated progressively by nodes
    tokens_in: int
    tokens_out: int
    cost_usd: float
    model: str
    node_trace: list[NodeTrace]

    # Control
    error: str | None
    guard_code: str | None               # machine-readable guard verdict
    status: str
