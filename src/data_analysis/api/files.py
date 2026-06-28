from fastapi import APIRouter
from sqlalchemy import select

from data_analysis.db.models import UploadedFile
from data_analysis.db.session import create_db_session
from data_analysis.domain.models import FileListItem, FileListResponse

router = APIRouter(prefix="/api")


@router.get("/files", response_model=FileListResponse)
def list_files():
    """List all uploaded files."""
    with create_db_session() as session:
        rows = (
            session.execute(
                select(UploadedFile).order_by(UploadedFile.created_at.desc())
            )
            .scalars()
            .all()
        )
        # Convert to domain models while still inside the session to avoid
        # DetachedInstanceError after the session closes.
        files = [
            FileListItem(
                file_id=r.id,
                original_filename=r.original_filename,
                file_size_bytes=r.file_size_bytes,
                row_count=r.row_count,
                column_count=r.column_count,
                created_at=r.created_at,
            )
            for r in rows
        ]
    return FileListResponse(files=files)
