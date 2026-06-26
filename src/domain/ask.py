from pydantic import BaseModel


class AskRequest(BaseModel):
    """Request body for `POST /ask`.

    Phase 2: single-dataset Q&A. Either `dataset_id` (one) or `dataset_ids`
    (explicit list) selects the dataset(s); `session_id` and `skip_clarification`
    are accepted for forward-compat but are not acted on until Phase 3.
    """

    question: str
    dataset_id: str | None = None
    dataset_ids: list[str] | None = None
    session_id: str | None = None
    skip_clarification: bool = False
