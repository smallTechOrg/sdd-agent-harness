from pydantic import BaseModel


class RunRequest(BaseModel):
    input_text: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    output_text: str | None = None
    error: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    model: str | None = None
    node_trace: list | None = None
