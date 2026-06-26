"""Dataset routes (Phase 2 subset).

List / detail / preview / delete for uploaded datasets. The session, context,
describe, re-derive, and clean routes belong to later phases and are not added
here. Cascade-to-derived deletion (C15) is Phase 4 — Phase 2 deletes the dataset
row, its on-disk CSV/Parquet, and its own `query_runs`.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import DatasetRow, QueryRunRow
from db.session import get_session
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.datasets")


def _dtype_alias(dtype: str) -> str:
    """Map a pandas dtype string to the spec's stable alias (spec/data.md)."""
    d = dtype.lower()
    if d.startswith("datetime"):
        return "datetime"
    if d.startswith("timedelta"):
        return "duration"
    if d.startswith("bool"):
        return "boolean"
    if d.startswith("category"):
        return "category"
    if d.startswith("int") or d.startswith("uint"):
        return "integer"
    if d.startswith("float"):
        return "float"
    # object / string / anything else -> text
    return "text"


def _columns_schema(columns_json) -> list[dict]:
    """Build `[{name, dtype-alias}]` from the stored columns_json.

    columns_json is `[{name, dtype}]` (as written at upload). Tolerates a bare
    list of names too.
    """
    schema: list[dict] = []
    for entry in columns_json or []:
        if isinstance(entry, dict):
            name = str(entry.get("name", ""))
            dtype = str(entry.get("dtype", "object"))
        else:
            name = str(entry)
            dtype = "object"
        schema.append({"name": name, "dtype": _dtype_alias(dtype)})
    return schema


def _column_names(columns_json) -> list[str]:
    names: list[str] = []
    for entry in columns_json or []:
        names.append(str(entry.get("name", "")) if isinstance(entry, dict) else str(entry))
    return names


def _list_item(row: DatasetRow) -> dict:
    return {
        "id": row.id,
        "filename": row.filename,
        "format": row.format,
        "row_count": row.row_count,
        "col_count": row.col_count,
        "columns": _column_names(row.columns_json),
        "origin": row.origin,
        "context": row.context,
        "auto_notes_status": row.auto_notes_status,
        # Phase-2 defaults — staleness / derivation arrive in Phase 4.
        "stale": False,
        "derived_from_run_id": row.derived_from_run_id,
        "derived_from_dataset_ids": row.derived_from_dataset_ids or [],
        "derivation_description": None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _format_cell(value):
    """Per-cell formatting for preview: floats round 4, whole floats -> int, NaN -> null."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if value.is_integer():
            return int(value)
        return round(value, 4)
    # numpy scalars surface as python types via .item() upstream; guard anyway
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _load_dataframe(row: DatasetRow) -> pd.DataFrame:
    """Load the dataset's DataFrame (Parquet preferred, CSV fallback)."""
    if row.parquet_path and Path(row.parquet_path).exists():
        return pd.read_parquet(row.parquet_path)
    return pd.read_csv(row.file_path)


def _delete_files(row: DatasetRow) -> None:
    for path_str in (row.file_path, row.parquet_path):
        if not path_str:
            continue
        try:
            Path(path_str).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("dataset_file_delete_failed", path=path_str, error=str(exc))


@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    rows = session.execute(
        select(DatasetRow).order_by(DatasetRow.created_at.desc())
    ).scalars().all()
    return ok([_list_item(r) for r in rows])


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("not_found", f"Dataset {dataset_id} not found", 404)
    item = _list_item(row)
    item["columns_schema"] = _columns_schema(row.columns_json)
    item["content_hash"] = row.content_hash
    item["file_path"] = row.file_path
    item["parquet_path"] = row.parquet_path
    item["derivation_code"] = row.derivation_code
    item["context_facts"] = row.context_facts or []
    return ok(item)


@router.get("/datasets/{dataset_id}/preview")
def preview_dataset(
    dataset_id: str,
    rows: int = Query(default=10),
    session: Session = Depends(get_session),
) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("not_found", f"Dataset {dataset_id} not found", 404)

    n = max(1, min(50, rows))
    try:
        df = _load_dataframe(row).head(n)
    except Exception as exc:
        logger.error("dataset_preview_read_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error("read_error", f"Could not read dataset: {exc}", 500)

    columns = [str(c) for c in df.columns]
    preview_rows = []
    for record in df.to_dict(orient="records"):
        preview_rows.append({str(k): _format_cell(v) for k, v in record.items()})
    return ok({"columns": columns, "rows": preview_rows})


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("not_found", f"Dataset {dataset_id} not found", 404)

    _delete_files(row)
    # Phase 2: delete the dataset's own runs (recursive-derived cascade is Phase 4).
    runs = session.execute(
        select(QueryRunRow).where(QueryRunRow.dataset_id == dataset_id)
    ).scalars().all()
    for r in runs:
        session.delete(r)
    session.delete(row)
    logger.info("dataset_deleted", dataset_id=dataset_id, runs_deleted=len(runs))
    return ok({"deleted": dataset_id})


@router.delete("/datasets")
def delete_all_datasets(session: Session = Depends(get_session)) -> dict:
    rows = session.execute(select(DatasetRow)).scalars().all()
    for row in rows:
        _delete_files(row)
        session.delete(row)
    # Phase 2: also clear single-dataset runs (no sessions yet).
    runs = session.execute(select(QueryRunRow)).scalars().all()
    for r in runs:
        session.delete(r)
    logger.info("datasets_deleted_all", count=len(rows))
    return ok({"deleted_count": len(rows)})
