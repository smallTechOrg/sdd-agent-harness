from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from data_analysis.db.models import UploadedFile
from data_analysis.db.session import create_db_session
from data_analysis.graph.runner import run_analysis_stream

router = APIRouter(prefix="/api/query")


class QueryRequest(BaseModel):
    question: str
    file_ids: list[str]
    session_id: str | None = None


@router.post("/stream")
def stream_query(req: QueryRequest):
    """Stream the analysis response as Server-Sent Events."""
    # Validate question
    if not req.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUESTION", "message": "Question cannot be empty"},
        )
    if len(req.question) > 2000:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "QUESTION_TOO_LONG",
                "message": "Question max 2000 chars",
            },
        )

    # Validate file_ids
    if not req.file_ids:
        raise HTTPException(
            status_code=400,
            detail={"code": "NO_FILES", "message": "At least one file_id required"},
        )

    # Verify all file_ids exist in the database
    with create_db_session() as session:
        for fid in req.file_ids:
            row = session.get(UploadedFile, fid)
            if row is None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "FILE_NOT_FOUND",
                        "message": f"File {fid!r} not found",
                    },
                )

    def event_stream():
        for chunk in run_analysis_stream(
            question=req.question,
            file_ids=req.file_ids,
            session_id=req.session_id,
        ):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
