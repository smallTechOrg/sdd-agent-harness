from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api._common import api_error
from data_analysis_agent.api._repository import get_data_source_or_404
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import (
    DataSourceRow,
    SessionDataSourceRow,
)
from data_analysis_agent.db.session import get_session
from data_analysis_agent.tools.descriptions import generate_tool_descriptions
from data_analysis_agent.tools.ingester import FileIngester, IngestResult
from data_analysis_agent.tools.mcp.pool import get_manager
from data_analysis_agent.tools.table_naming import sql_table_name

log = structlog.get_logger()
router = APIRouter()

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".json")


@router.post("/datasources/upload")
def upload_data_source(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Convert an uploaded file to Parquet, register a data source + tool, redirect home."""
    filename = file.filename or ""
    _require_supported_extension(filename)
    ds = DataSourceRow(name=filename, type="csv")
    session.add(ds)
    session.flush()

    result = _ingest_to_parquet(session, file, ds.id)
    _apply_ingest_metadata(ds, result)
    table_name = sql_table_name(filename)
    descriptions = generate_tool_descriptions(
        filename, table_name, ds.schema, ds.row_count or 0, result.parquet_path
    )
    ds.tool_description = descriptions.tool
    ds.capability_description = descriptions.capability
    _log_upload(ds.id, filename, table_name, result)
    return RedirectResponse(url="/", status_code=303)


@router.post("/datasources/{datasource_id}/sync")
def sync_data_source(
    request: Request,
    datasource_id: str,
    session: Session = Depends(get_session),
):
    """Re-generate the tool and capability descriptions from the stored Parquet; redirect home."""
    ds = get_data_source_or_404(session, datasource_id)
    _require_parquet(ds)
    table_name = sql_table_name(ds.name)
    descriptions = generate_tool_descriptions(
        ds.name, table_name, ds.schema, ds.row_count or 0, ds.parquet_path
    )
    ds.tool_description = descriptions.tool
    ds.capability_description = descriptions.capability
    log.info("datasource.synced", datasource_id=datasource_id, filename=ds.name)
    return RedirectResponse(url="/", status_code=303)


@router.post("/datasources/{datasource_id}/delete")
def delete_data_source(
    request: Request,
    datasource_id: str,
    session: Session = Depends(get_session),
):
    """Delete a data source, its session links, and its Parquet file."""
    ds = get_data_source_or_404(session, datasource_id)
    _close_pools_using(session, datasource_id)  # sessions querying this source now have a stale pool
    _unlink_from_sessions(session, datasource_id)
    if ds.parquet_path:
        Path(ds.parquet_path).unlink(missing_ok=True)
    session.delete(ds)
    log.info("datasource.deleted", datasource_id=datasource_id)
    return RedirectResponse(url="/", status_code=303)


def _require_supported_extension(filename: str) -> None:
    """Raise a recoverable API error if the filename has an unsupported extension."""
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise api_error("INVALID_FILE", f"Supported file types: {', '.join(SUPPORTED_EXTENSIONS)}")


def _ingest_to_parquet(session: Session, file: UploadFile, ds_id: str) -> IngestResult:
    """Stream the upload straight to Parquet; roll back and 400 on parse failure."""
    parquet_dir = Path(get_settings().upload_dir) / "parquet"
    suffix = Path(file.filename or "").suffix.lower()
    try:
        return FileIngester().ingest_stream(file.file, suffix, parquet_dir, ds_id)
    except Exception as exc:
        session.rollback()
        raise api_error("PARSE_FAILED", f"Could not process file: {exc}")


def _apply_ingest_metadata(ds: DataSourceRow, result: IngestResult) -> None:
    """Copy Parquet path, row count, columns, and schema onto the data source row."""
    ds.parquet_path = result.parquet_path
    ds.row_count = result.row_count
    ds.column_names = result.column_names
    ds.schema_json = result.schema_json


def _require_parquet(ds: DataSourceRow) -> None:
    """Raise a recoverable API error if the source's Parquet file is missing."""
    if not ds.parquet_path or not Path(ds.parquet_path).exists():
        raise api_error("NO_PARQUET", "Parquet file is missing — re-upload the data source.")


def _close_pools_using(session: Session, datasource_id: str) -> None:
    """Close the MCP pool of every session that includes this data source."""
    links = (
        session.query(SessionDataSourceRow)
        .filter(SessionDataSourceRow.data_source_id == datasource_id)
        .all()
    )
    manager = get_manager()
    for link in links:
        manager.close(link.session_id)


def _unlink_from_sessions(session: Session, datasource_id: str) -> None:
    """Remove all session join-table rows referencing a data source."""
    session.query(SessionDataSourceRow).filter(
        SessionDataSourceRow.data_source_id == datasource_id
    ).delete()


def _log_upload(ds_id: str, filename: str, table_name: str, result: IngestResult) -> None:
    """Emit the structured success log for a completed upload."""
    log.info(
        "upload.success",
        data_source_id=ds_id,
        filename=filename,
        table=table_name,
        parquet_path=result.parquet_path,
        rows=result.row_count,
        parquet_bytes=result.file_size_bytes,
    )
