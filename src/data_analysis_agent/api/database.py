from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Body, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import api_error, render
from data_analysis_agent.api._repository import get_database_or_404
from data_analysis_agent.api._view import spa_context
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import (
    McpPromptRow,
    McpResourceRow,
    DatabaseRow,
    McpToolRow,
    SessionDatabaseRow,
)
from data_analysis_agent.db.session import create_db_session, get_session
from data_analysis_agent.tools.connectors.base import EXTERNAL_TYPES, DatasetConnectionError, get_connector
from data_analysis_agent.tools.connectors.uri import DatasetURI
from data_analysis_agent.tools.ingester import FileIngester
from data_analysis_agent.tools.mcp.dispatch import MUTATION_METHODS, handle_jsonrpc
from data_analysis_agent.tools.mcp.pool import get_manager
from data_analysis_agent.tools.sync import apply_sync_result, run_sync
from data_analysis_agent.tools.table_naming import sql_table_name

log = structlog.get_logger()
router = APIRouter()

SUPPORTED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".json")


# --- Upload (auxiliary): file → Parquet, returns the data URI ----------------

@router.post("/database/upload")
def upload_csv(
    database_name: Annotated[str, Form()] = "",
    file: UploadFile | None = File(None),
):
    """Convert an uploaded file to Parquet under the named database's directory; return its data URI.

    Creates **no entity** — this is the file-staging step the UI calls before ``POST /database`` (a new
    database) or, for an existing database, before ``POST /database/{id}/sync`` (adding a table).
    """
    name = database_name.strip()
    if not name:
        raise api_error("INVALID_NAME", "Database name is required.")
    if file is None or not (file.filename or ""):
        raise api_error("NO_FILE", "Choose a CSV/XLSX/JSON file to upload.")
    _require_supported_extension(file.filename or "")
    directory = _database_dir(name)
    table = _unique_table_name(directory, file.filename or "data.csv")
    suffix = Path(file.filename or "").suffix.lower()
    try:
        FileIngester().ingest_stream(file.file, suffix, directory, table)
    except Exception as exc:
        raise api_error("PARSE_FAILED", f"Could not process file: {exc}")
    log.info("database.upload", database=name, table=table)
    return JSONResponse({"uri": _parquet_uri(name), "table": table})


# --- Create: build the database from a URI + type, then run sync -------------

@router.post("/database")
def create_database(
    database_uri: Annotated[str, Form()] = "",
    database_type: Annotated[str, Form()] = "parquet",
    name: Annotated[str, Form()] = "",
    session: Session = Depends(get_session),
):
    """Create a **database** (an instance of an MCP-server type) from a URI + type.

    Both internal (parquet) and external (postgres) follow the same path: derive name/URI, enforce the
    1:1 name+URI constraint, create the row, **connection-check via the type's connector** (which
    abstracts directory/connection validation — zero tables is valid), then run the sync pipeline.
    """
    dtype = (database_type or "parquet").strip().lower()
    uri = database_uri.strip()
    nm = name.strip() or (DatasetURI(uri).database if uri else "")
    if not nm:
        raise api_error("INVALID_NAME", "Database name is required.")
    if dtype != "parquet" and dtype not in EXTERNAL_TYPES:
        raise api_error("INVALID_TYPE", f"Unsupported database type: {dtype!r}.")
    if dtype == "parquet":
        uri = _parquet_uri(nm)                       # canonical internal URI (derived from the name)
    elif not uri:
        raise api_error("NO_URI", "Provide a database connection URI.")

    _reject_duplicates(session, nm, uri)
    server = DatabaseRow(name=nm, type=dtype, uri=uri)
    session.add(server)
    session.flush()
    _connection_check_or_400(server)
    server.connection_error = None
    _generate(session, server)
    log.info("database.created", database_id=server.id, name=nm, type=dtype,
             uri=DatasetURI(uri).display())
    return RedirectResponse(url="/", status_code=303)


# --- Sync: regenerate capabilities (versioned, soft-delete) -----------------

@router.post("/database/{database_id}/sync")
def sync_database(database_id: str, session: Session = Depends(get_session)):
    """Re-run the 5-stage pipeline (connector re-inspects tables), apply (version++, soft-delete),
    refresh pools. This is also how a newly-uploaded table is picked up (upload → sync)."""
    server = get_database_or_404(session, database_id)
    _connection_check_or_400(server)
    server.connection_error = None
    _generate(session, server)
    get_manager().close_sessions_for_database(database_id)
    log.info("database.synced", database_id=database_id, name=server.name, version=server.version)
    return RedirectResponse(url="/", status_code=303)


# --- MCP JSON-RPC dispatch --------------------------------------------------

@router.post("/database/{database_id}")
def mcp_dispatch(database_id: str, payload: Annotated[dict, Body(...)]):
    """Single MCP JSON-RPC 2.0 endpoint over the database's stored tools/resources/prompts.

    Manages its own session so a failed mutation persists nothing (handlers roll back) and a successful
    mutation refreshes the agent's pools **after** the commit (avoids holding the txn while taking the
    per-session lock).
    """
    method = payload.get("method", "") if isinstance(payload, dict) else ""
    with create_db_session() as session:
        server = get_database_or_404(session, database_id)
        response = handle_jsonrpc(session, server, payload)
    if method in MUTATION_METHODS and isinstance(response, dict) and "error" not in response:
        get_manager().close_sessions_for_database(database_id)
    return JSONResponse(response)


# --- Detail + delete --------------------------------------------------------

@router.get("/database/{database_id}")
def database_detail(request: Request, database_id: str, session: Session = Depends(get_session)):
    """Render the single-page shell with this database active on the Database tab."""
    server = get_database_or_404(session, database_id)
    ctx = spa_context(session, active_tab="database", active_server=server)
    return render(request, templates, "index.html", **ctx)


@router.post("/database/{database_id}/delete")
def delete_database(database_id: str, session: Session = Depends(get_session)):
    """Delete a database, its capability rows + session links, and its on-disk directory."""
    server = get_database_or_404(session, database_id)
    get_manager().close_sessions_for_database(database_id)
    session.query(SessionDatabaseRow).filter(
        SessionDatabaseRow.database_id == database_id
    ).delete()
    for model in (McpToolRow, McpResourceRow, McpPromptRow):
        session.query(model).filter(model.database_id == database_id).delete()
    name = server.name
    session.delete(server)
    shutil.rmtree(_database_dir(name), ignore_errors=True)
    log.info("database.deleted", database_id=database_id)
    return RedirectResponse(url="/", status_code=303)


# --- internals --------------------------------------------------------------

def _generate(session: Session, server: DatabaseRow) -> None:
    """Run the sync pipeline and apply it transactionally (caller's session commits)."""
    result = run_sync(session, server)
    apply_sync_result(session, server, result)


def _connection_check_or_400(server: DatabaseRow) -> None:
    """Run the database's connection-check via its connector; 400 (credential-free) on failure."""
    try:
        get_connector(_server_dict(server)).connection_check()
    except DatasetConnectionError as exc:
        raise api_error("CONNECTION_FAILED", str(exc))


def _unique_table_name(directory: Path, filename: str) -> str:
    """SQL-safe table name from a filename, auto-suffixed on collision within the directory."""
    base = sql_table_name(filename)
    existing = {p.stem for p in directory.glob("*.parquet")} if directory.exists() else set()
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


def _reject_duplicates(session: Session, name: str, uri: str) -> None:
    """Enforce 1:1 dataset↔database: reject a duplicate name or URI (API-level, before flush)."""
    if session.query(DatabaseRow).filter(DatabaseRow.name == name).first():
        raise api_error("DUPLICATE_NAME", f"A database named '{name}' already exists.")
    if session.query(DatabaseRow).filter(DatabaseRow.uri == uri).first():
        raise api_error("DUPLICATE_URI", "A database already exists for this URI.")


def _require_supported_extension(filename: str) -> None:
    if not any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise api_error("INVALID_FILE", f"Supported file types: {', '.join(SUPPORTED_EXTENSIONS)}")


def _server_dict(server: DatabaseRow) -> dict:
    return {"id": server.id, "name": server.name, "type": server.type, "uri": server.uri}


def _database_dir(name: str) -> Path:
    """The on-disk directory holding a parquet database's Parquet files: ``{datasets_dir}/{slug(name)}``."""
    return Path(get_settings().datasets_dir) / sql_table_name(name)


def _parquet_uri(name: str) -> str:
    from urllib.parse import quote
    return f"parquet:///{quote(name, safe='')}"
