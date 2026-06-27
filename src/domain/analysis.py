from pydantic import BaseModel

from db.models import AnalysisRow


class AnalysisRequest(BaseModel):
    """The JSON body for POST /analyses (per spec/api.md)."""

    dataset_id: str
    question: str


class AnalysisResponse(BaseModel):
    """The `data` payload returned by POST /analyses and GET /analyses/{id}.

    Maps the persisted `analyses` row's column names onto the documented API
    field names: ``generated_code`` -> ``code``, ``execution_steps`` -> ``steps``,
    ``execution_result`` -> ``result_value``, ``id`` -> ``analysis_id``.
    """

    analysis_id: str
    dataset_id: str
    question: str
    status: str
    answer: str | None = None
    code: str | None = None
    steps: str | None = None
    result_value: str | None = None
    attempts: int = 0

    @classmethod
    def from_row(cls, row: AnalysisRow) -> "AnalysisResponse":
        return cls(
            analysis_id=row.id,
            dataset_id=row.dataset_id,
            question=row.question,
            status=row.status,
            answer=row.answer,
            code=row.generated_code,
            steps=row.execution_steps,
            result_value=row.execution_result,
            attempts=row.attempts,
        )
