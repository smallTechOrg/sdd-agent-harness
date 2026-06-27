from pydantic import BaseModel


class AnalysisRequest(BaseModel):
    dataset_id: str
    question: str


class AnalysisResponse(BaseModel):
    dataset_id: str
    chart_type: str
    labels: list[str]
    values: list[float]
    summary: str
