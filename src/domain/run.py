from pydantic import BaseModel


class RunRequest(BaseModel):
    input_text: str
    conversation_id: str = ""   # set to chat across turns (session memory)


class RunResponse(BaseModel):
    run_id: str
    status: str
    output_text: str | None = None
    error: str | None = None
    guard_code: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None
    model: str | None = None
    node_trace: list | None = None
