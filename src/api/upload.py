import csv
import io
import json
import re
import time

from fastapi import APIRouter, UploadFile, File

from api._common import ok, api_error
from db.session import create_db_session
from db.models import UploadSession
from domain.run import UploadResponse
from observability.events import get_logger
from sqlalchemy import text

router = APIRouter()
_log = get_logger("api.upload")

_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


def infer_column_type(values: list) -> str:
    """Infer SQLite column type from a list of sample values (all non-empty)."""
    if not values:
        return "TEXT"
    for v in values:
        try:
            int(v)
        except (ValueError, TypeError):
            break
    else:
        return "INTEGER"
    for v in values:
        try:
            float(v)
        except (ValueError, TypeError):
            return "TEXT"
    return "REAL"


def _sanitize_name(name: str, max_len: int = 40) -> str:
    """Convert an arbitrary string to a safe SQL identifier."""
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:max_len] if name else "file"


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict:
    t0 = time.monotonic()

    # Extension check
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith(".csv"):
        raise api_error("UNSUPPORTED_FORMAT", "Only .csv files are accepted.", 422)

    # Read content
    content = await file.read()
    if len(content) > _MAX_FILE_BYTES:
        raise api_error("FILE_TOO_LARGE", "File exceeds 50 MB limit.", 413)

    # Parse CSV
    text_content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content))

    if not reader.fieldnames:
        raise api_error("INVALID_CSV", "CSV file has no header row.", 422)

    headers = list(reader.fieldnames)

    if len(headers) > 200:
        raise api_error("INVALID_CSV", f"CSV has {len(headers)} columns; maximum supported is 200.", 422)

    rows = list(reader)

    if not rows:
        raise api_error("INVALID_CSV", "CSV file has no data rows.", 422)

    # Infer column types by scanning ALL non-empty values per column
    col_types: dict[str, str] = {}
    for col in headers:
        non_empty_vals = [
            (row.get(col) or "").strip()
            for row in rows
            if (row.get(col) or "").strip()
        ]
        col_types[col] = infer_column_type(non_empty_vals)

    # Build table name
    stem = re.sub(r"\.csv$", "", filename, flags=re.IGNORECASE)

    with create_db_session() as session:
        # We need the session ID before we name the table
        upload = UploadSession(
            table_name="__placeholder__",
            original_filename=filename,
            row_count=0,
            col_count=len(headers),
            schema_json="[]",
        )
        session.add(upload)
        session.flush()  # get the id assigned
        session_id = upload.id

        safe_stem = _sanitize_name(stem)
        table_name = f"{safe_stem}_{session_id[:8]}"

        # Create dynamic table
        col_defs = ", ".join(
            f'"{col}" {col_types.get(col, "TEXT")}' for col in headers
        )
        ddl = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({col_defs})'
        session.execute(text(ddl))

        # Insert rows in batches
        if rows:
            placeholders = ", ".join(f":col_{i}" for i in range(len(headers)))
            insert_sql = f'INSERT INTO "{table_name}" ({", ".join(f"{chr(34)}{h}{chr(34)}" for h in headers)}) VALUES ({placeholders})'

            batch = []
            for row in rows:
                param_row = {}
                for i, col in enumerate(headers):
                    raw = (row.get(col) or "").strip()
                    if raw == "":
                        param_row[f"col_{i}"] = None
                    elif col_types.get(col) == "INTEGER":
                        try:
                            param_row[f"col_{i}"] = int(raw)
                        except ValueError:
                            param_row[f"col_{i}"] = raw
                    elif col_types.get(col) == "REAL":
                        try:
                            param_row[f"col_{i}"] = float(raw)
                        except ValueError:
                            param_row[f"col_{i}"] = raw
                    else:
                        param_row[f"col_{i}"] = raw
                batch.append(param_row)

            session.execute(text(insert_sql), batch)

        schema = [{"column": col, "type": col_types.get(col, "TEXT")} for col in headers]

        upload.table_name = table_name
        upload.row_count = len(rows)
        upload.schema_json = json.dumps(schema)

    duration_ms = int((time.monotonic() - t0) * 1000)
    _log.info(
        "upload.done",
        table_name=table_name,
        row_count=len(rows),
        col_count=len(headers),
        duration_ms=duration_ms,
    )

    return ok(
        UploadResponse(
            session_id=session_id,
            table_name=table_name,
            row_count=len(rows),
            schema=schema,
        ).model_dump(by_alias=True)
    )
