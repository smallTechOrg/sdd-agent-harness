import io
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, UTC

import aiosqlite
import duckdb
import pandas as pd
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from src.config import get_settings

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _error(status: int, code: str, message: str) -> JSONResponse:
    """Return spec-canonical error envelope: {"error": {"code": ..., "message": ...}}."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

ALLOWED_EXTENSIONS = {".csv", ".json", ".xlsx", ".xls", ".parquet"}


def _detect_format(filename: str) -> str | None:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".csv":
        return "csv"
    if ext == ".json":
        return "json"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext == ".parquet":
        return "parquet"
    return None


def _build_column_schema(df: pd.DataFrame) -> list[dict]:
    """Build column_schema per spec: name, dtype, nullable, sample."""
    schema = []
    for col in df.columns:
        series = df[col]
        dtype_str = str(series.dtype)
        # Map pandas dtypes to friendly strings
        if "int" in dtype_str:
            dtype = "INTEGER"
        elif "float" in dtype_str:
            dtype = "DOUBLE"
        elif "bool" in dtype_str:
            dtype = "BOOLEAN"
        else:
            dtype = "TEXT"
        nullable = bool(series.isna().any())
        first_valid = series.dropna().iloc[0] if len(series.dropna()) > 0 else None
        sample = str(first_valid) if first_valid is not None else None
        schema.append({"name": col, "dtype": dtype, "nullable": nullable, "sample": sample})
    return schema


async def _ingest_to_duckdb(df: pd.DataFrame, table_name: str, duckdb_path: str) -> None:
    """Write DataFrame to a persistent DuckDB table [C-DUCKDB-VIEW: use TABLE not VIEW]."""
    # Ensure parent directory exists [C-DB-DIRNAME]
    data_dir = os.path.dirname(duckdb_path)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
    con = duckdb.connect(duckdb_path)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
    finally:
        con.close()


@router.post("", status_code=201)
async def upload_dataset(
    session_id: str,
    file: UploadFile = File(...),
):
    settings = get_settings()

    # Validate session exists
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cursor = await db.execute("SELECT id FROM session WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if not row:
            return _error(404, "NO_SESSION", "Session not found")

    # Validate file type by extension
    filename = file.filename or "upload"
    file_format = _detect_format(filename)
    if file_format is None:
        return _error(422, "UNSUPPORTED_FILE", f"File type not supported: {filename}")

    # Read content
    content = await file.read()
    size_bytes = len(content)
    if size_bytes > settings.max_upload_bytes:
        return _error(413, "FILE_TOO_LARGE", "File exceeds 200 MB limit")

    # Parse into DataFrame
    try:
        if file_format == "csv":
            df = pd.read_csv(io.BytesIO(content))
        elif file_format == "json":
            df = pd.read_json(io.BytesIO(content))
        elif file_format == "excel":
            # [C-EXCEL-TMP]: use tempfile, always clean up
            tmpdir = tempfile.mkdtemp()
            try:
                tmp_path = os.path.join(tmpdir, filename)
                with open(tmp_path, "wb") as f:
                    f.write(content)
                df = pd.read_excel(tmp_path)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
        elif file_format == "parquet":
            df = pd.read_parquet(io.BytesIO(content))
        else:
            return _error(422, "UNSUPPORTED_FILE", "Unsupported format")
    except Exception as e:
        return _error(422, "PARSE_ERROR", str(e))

    dataset_id = str(uuid.uuid4())
    table_name = f"dataset_{dataset_id.replace('-', '_')}"
    now = datetime.now(UTC).isoformat()

    # Ingest to DuckDB [C-DUCKDB-VIEW: persistent TABLE, not VIEW]
    try:
        await _ingest_to_duckdb(df, table_name, settings.duckdb_path)
    except Exception as e:
        return _error(500, "INTERNAL", f"DuckDB ingest failed: {e}")

    column_schema = _build_column_schema(df)
    column_names_json = json.dumps([c["name"] for c in column_schema])

    # Register in SQLite
    async with aiosqlite.connect(settings.sqlite_path) as db:
        await db.execute(
            "INSERT INTO dataset (id, session_id, name, file_format, row_count, column_names, duckdb_table, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, session_id, filename, file_format, len(df), column_names_json, table_name, now),
        )
        await db.commit()

    response = JSONResponse(
        status_code=201,
        content={
            "id": dataset_id,
            "name": filename,
            "file_format": file_format,
            "row_count": len(df),
            "size_bytes": size_bytes,
            "column_schema": column_schema,
            "duckdb_table": table_name,
            "uploaded_at": now,
        },
    )
    response.headers["Location"] = f"/datasets/{dataset_id}"
    return response


@router.get("")
async def list_datasets(session_id: str):
    settings = get_settings()
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        # Validate session
        cursor = await db.execute("SELECT id FROM session WHERE id = ?", (session_id,))
        if not await cursor.fetchone():
            return _error(404, "NO_SESSION", "Session not found")
        cursor = await db.execute(
            "SELECT id, name, file_format, row_count, column_names, duckdb_table, created_at "
            "FROM dataset WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        )
        rows = await cursor.fetchall()

    return {
        "datasets": [
            {
                "id": row["id"],
                "name": row["name"],
                "file_format": row["file_format"],
                "row_count": row["row_count"],
                "column_schema": [{"name": c, "dtype": "TEXT", "nullable": False, "sample": None}
                                  for c in json.loads(row["column_names"])],
                "duckdb_table": row["duckdb_table"],
                "uploaded_at": row["created_at"],
            }
            for row in rows
        ]
    }
