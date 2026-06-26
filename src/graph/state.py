from typing import TypedDict


class NodeTrace(TypedDict):
    node: str
    duration_ms: float


class AgentState(TypedDict, total=False):
    # Identity
    run_id: str

    # Input
    input_text: str

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
    status: str
