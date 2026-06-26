from pydantic import BaseModel


class RunRequest(BaseModel):
    csv_text: str
    question: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    answer: str | None = None
    explanation: str | None = None
    generated_code: str | None = None
    result_table: dict | None = None
    truncated: bool = False
    error: str | None = None
