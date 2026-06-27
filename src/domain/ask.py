from pydantic import BaseModel


class AskRequest(BaseModel):
    dataset_id: str
    question: str


class AskResponse(BaseModel):
    question_id: str
    answer_text: str | None = None
    chart_spec: dict | None = None
    status: str
