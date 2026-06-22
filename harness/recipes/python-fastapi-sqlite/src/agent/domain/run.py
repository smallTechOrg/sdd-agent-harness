from pydantic import BaseModel


class RunRequest(BaseModel):
    input_text: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    output_text: str | None = None
