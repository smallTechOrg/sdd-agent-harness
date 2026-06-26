from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    csv_text: str
    question: str
    mode: str = Field(default="pandas", description="Analysis mode: 'pandas' or 'sql'")


class RunResponse(BaseModel):
    run_id: str
    status: str
    mode: str = "pandas"
    answer: str | None = None
    explanation: str | None = None
    generated_code: str | None = None
    result_table: dict | None = None
    truncated: bool = False
    error: str | None = None
