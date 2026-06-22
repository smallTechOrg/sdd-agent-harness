from __future__ import annotations

import json
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
    ToolCapabilityRow,
    ToolRow,
)
from data_analysis_agent.db.session import get_session
from data_analysis_agent.tools.descriptions import ToolDescriptions, generate_tool_descriptions
from data_analysis_agent.tools.ingester import FileIngester, IngestResult
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
    _register_tool(session, ds.id, table_name, result.parquet_path, descriptions)
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
    tool = session.query(ToolRow).filter(ToolRow.data_source_id == datasource_id).first()
    if not tool:
        raise api_error("NO_TOOL", "No tool registered for this data source.")

    table_name = tool.config.get("table_name", "data")
    descriptions = generate_tool_descriptions(
        ds.name, table_name, ds.schema, ds.row_count or 0, ds.parquet_path
    )
    _apply_descriptions(session, tool, descriptions)
    log.info("datasource.synced", datasource_id=datasource_id, filename=ds.name)
    return RedirectResponse(url="/", status_code=303)


@router.post("/datasources/{datasource_id}/delete")
def delete_data_source(
    request: Request,
    datasource_id: str,
    session: Session = Depends(get_session),
):
    """Delete a data source and its tools, capabilities, session links, and Parquet file."""
    ds = get_data_source_or_404(session, datasource_id)
    _unlink_from_sessions(session, datasource_id)
    _delete_tools(session, datasource_id)
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


def _register_tool(
    session: Session,
    ds_id: str,
    table_name: str,
    parquet_path: str,
    descriptions: ToolDescriptions,
) -> None:
    """Create the ``csv_query`` tool and its ``run_query`` capability for a source."""
    tool = ToolRow(
        data_source_id=ds_id,
        name="csv_query",
        type="csv_query",
        description=descriptions.tool,
        config_json=json.dumps({"table_name": table_name, "parquet_path": parquet_path}),
    )
    session.add(tool)
    session.flush()
    session.add(_build_capability(tool.id, table_name, descriptions.capability))


def _build_capability(tool_id: str, table_name: str, description: str) -> ToolCapabilityRow:
    """Build the ``run_query`` capability row for a tool."""
    return ToolCapabilityRow(
        tool_id=tool_id,
        name="run_query",
        description=description,
        parameter_schema_json=json.dumps({
            "query": {
                "type": "string",
                "description": f"A valid SQL SELECT statement. Table name is '{table_name}'.",
            }
        }),
    )


def _apply_descriptions(session: Session, tool: ToolRow, descriptions: ToolDescriptions) -> None:
    """Update the tool and all its capability descriptions in place."""
    tool.description = descriptions.tool
    for cap in session.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == tool.id).all():
        cap.description = descriptions.capability


def _require_parquet(ds: DataSourceRow) -> None:
    """Raise a recoverable API error if the source's Parquet file is missing."""
    if not ds.parquet_path or not Path(ds.parquet_path).exists():
        raise api_error("NO_PARQUET", "Parquet file is missing — re-upload the data source.")


def _unlink_from_sessions(session: Session, datasource_id: str) -> None:
    """Remove all session join-table rows referencing a data source."""
    session.query(SessionDataSourceRow).filter(
        SessionDataSourceRow.data_source_id == datasource_id
    ).delete()


def _delete_tools(session: Session, datasource_id: str) -> None:
    """Delete every tool and its capabilities registered against a data source."""
    tools = session.query(ToolRow).filter(ToolRow.data_source_id == datasource_id).all()
    for tool in tools:
        session.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == tool.id).delete()
        session.delete(tool)


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
