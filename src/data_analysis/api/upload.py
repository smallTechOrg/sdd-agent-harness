import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from data_analysis.api._common import api_error
from data_analysis.db.models import UploadedFile
from data_analysis.db.session import create_db_session
from data_analysis.domain.models import UploadResponse
from data_analysis.tools.profiler import profile_csv

router = APIRouter(prefix="/api/files")

UPLOAD_DIR = Path("uploads")
MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
):
    """Upload a CSV or Excel file, profile it, and return the profile."""
    # Validate extension
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise api_error(
            "INVALID_FILE_TYPE",
            f"File must be .csv or .xlsx, got {ext!r}",
        )

    # Read file bytes
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise api_error("FILE_TOO_LARGE", "File exceeds 100 MB limit", status_code=413)

    # Save to disk
    UPLOAD_DIR.mkdir(exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{ext}"
    file_path.write_bytes(content)

    # Profile
    try:
        if ext == ".csv":
            profile = profile_csv(str(file_path), len(content))
        else:
            # Phase 3: Excel support — not yet implemented
            raise api_error("UNSUPPORTED_FORMAT", "Excel upload is coming in Phase 3")
    except Exception as e:
        file_path.unlink(missing_ok=True)
        if hasattr(e, "status_code"):
            raise
        raise api_error(
            "PROFILE_FAILED",
            f"Failed to profile file: {e}",
            status_code=500,
        )

    # Persist metadata
    profile_dict = profile.model_dump()
    with create_db_session() as session:
        row = UploadedFile(
            id=file_id,
            original_filename=filename,
            file_ext=ext.lstrip("."),
            file_path=str(file_path),
            file_size_bytes=len(content),
            row_count=profile.row_count,
            column_count=profile.column_count,
            profile_json=json.dumps(profile_dict),
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)

    return UploadResponse(
        file_id=file_id,
        original_filename=filename,
        profile=profile,
    )
