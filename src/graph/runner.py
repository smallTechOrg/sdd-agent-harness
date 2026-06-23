"""Runner: orchestrates one ask through the agent graph and persists the audit row.

``run_agent(dataset_id, question, session_id=None, db_session=None) -> dict``
returns the /ask response payload.
"""
from __future__ import annotations

import logging
from contextlib import nullcontext

from graph.agent import agentic_ai
from graph.state import AgentState

logger = logging.getLogger(__name__)


def run_agent(
    dataset_id: str,
    question: str,
    session_id: str | None = None,
    db_session=None,
) -> dict:
    """Run one NL question over one dataset and return the /ask payload dict.

    Steps: resolve/create session -> create pending audit row (id == run_id) ->
    load DatasetRow.duckdb_table -> invoke graph -> finalize audit row -> return.

    Returns a dict with keys:
      run_id, narrative, sql, columns, rows, row_count, duration_ms, status,
      error (None on success), dataset_id, session_id.
    """
    from config.settings import get_settings
    from db.session import create_db_session
    from db.models import DatasetRow

    settings = get_settings()

    owns_session = db_session is None
    session_cm = create_db_session() if owns_session else nullcontext(db_session)

    with session_cm as db:
        # 1. Resolve dataset (must exist; unknown -> ValueError -> 400).
        dataset = db.get(DatasetRow, dataset_id)
        if dataset is None:
            raise ValueError(f"Unknown dataset_id: {dataset_id}")

        # 2. Resolve / create session.
        resolved_session_id = session_id or dataset.session_id
        if not resolved_session_id:
            resolved_session_id = _ensure_session(db)

        # 3. Create the pending audit row (id == run_id).
        run_id = _create_pending_audit(
            db,
            session_id=resolved_session_id,
            dataset_id=dataset_id,
            nl_question=question,
        )

        table_name = dataset.duckdb_table

    # 4. Build initial state and invoke the graph.
    initial: AgentState = {
        "run_id": run_id,
        "session_id": resolved_session_id,
        "dataset_id": dataset_id,
        "nl_question": question,
        "duckdb_path": settings.duckdb_path,
        "max_sample_rows": int(settings.max_sample_rows),
        "table_name": table_name,
        "error": None,
    }

    try:
        final: dict = agentic_ai.invoke(initial)
    except Exception as exc:  # noqa: BLE001 - never lose the audit row
        logger.exception("graph invocation crashed for run %s", run_id)
        final = {**initial, "status": "failed", "error": str(exc)}

    status = final.get("status") or ("failed" if final.get("error") else "completed")
    error_message = final.get("error")
    generated_sql = final.get("generated_sql")
    row_count = final.get("row_count")
    duration_ms = final.get("duration_ms")
    narrative = final.get("narrative")
    columns = final.get("result_columns") or []
    rows = final.get("result_rows") or []

    # 5. Finalize the audit row (always written).
    finalize_cm = create_db_session() if owns_session else nullcontext(db_session)
    with finalize_cm as db:
        _finalize_audit(
            db,
            run_id=run_id,
            session_id=resolved_session_id,
            dataset_id=dataset_id,
            nl_question=question,
            generated_sql=generated_sql,
            row_count=row_count,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
        )

    return {
        "run_id": run_id,
        "narrative": narrative,
        "sql": generated_sql,
        "columns": list(columns),
        "rows": rows,
        "row_count": row_count if row_count is not None else 0,
        "duration_ms": duration_ms if duration_ms is not None else 0,
        "status": status,
        "error": error_message,
        "dataset_id": dataset_id,
        "session_id": resolved_session_id,
    }


# --------------------------------------------------------------------------- #
# Audit-service adapters (defensive against the sibling slice's signature)
# --------------------------------------------------------------------------- #
def _create_pending_audit(db, *, session_id, dataset_id, nl_question) -> str:
    """Create a pending audit row and return its id (== run_id).

    Adapts to either a `create_audit_pending(...)` helper or `write_audit(...)`
    upsert, or falls back to writing the AuditLogRow directly. The run_id is
    generated here so it can seed both the audit row and the graph state.
    """
    from uuid import uuid4

    from services import audit as audit_svc

    run_id = str(uuid4())

    fn = getattr(audit_svc, "create_audit_pending", None)
    if callable(fn):
        result = _try_call(
            fn,
            db,
            run_id=run_id,
            session_id=session_id,
            dataset_id=dataset_id,
            nl_question=nl_question,
        )
        return _extract_id(result) or run_id

    write_fn = getattr(audit_svc, "write_audit", None)
    if callable(write_fn):
        result = _try_call(
            write_fn,
            db,
            run_id=run_id,
            session_id=session_id,
            dataset_id=dataset_id,
            nl_question=nl_question,
            status="pending",
        )
        return _extract_id(result) or run_id

    # Fallback: write a pending row directly via the model.
    from db.models import AuditLogRow

    row = AuditLogRow(
        id=run_id,
        session_id=session_id,
        dataset_id=dataset_id,
        nl_question=nl_question,
        status="pending",
    )
    db.add(row)
    db.flush()
    return row.id


def _finalize_audit(
    db,
    *,
    run_id,
    session_id,
    dataset_id,
    nl_question,
    generated_sql,
    row_count,
    duration_ms,
    status,
    error_message,
) -> None:
    """Finalize the audit row, adapting to whatever the service exposes."""
    from services import audit as audit_svc

    finalize_fn = getattr(audit_svc, "finalize_audit", None)
    if callable(finalize_fn):
        _try_call(
            finalize_fn,
            db,
            run_id=run_id,
            session_id=session_id,
            dataset_id=dataset_id,
            nl_question=nl_question,
            generated_sql=generated_sql,
            row_count=row_count,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
        )
        return

    write_fn = getattr(audit_svc, "write_audit", None)
    if callable(write_fn):
        _try_call(
            write_fn,
            db,
            run_id=run_id,
            session_id=session_id,
            dataset_id=dataset_id,
            nl_question=nl_question,
            generated_sql=generated_sql,
            row_count=row_count,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
        )
        return

    # Fallback: update the model row directly.
    from db.models import AuditLogRow

    row = db.get(AuditLogRow, run_id)
    if row is not None:
        row.generated_sql = generated_sql
        row.row_count = row_count
        row.duration_ms = duration_ms
        row.status = status
        row.error_message = error_message
        db.flush()


def _ensure_session(db) -> str:
    """Resolve or create the default session id."""
    from services import ingest as ingest_svc

    fn = getattr(ingest_svc, "get_or_create_default_session", None)
    if callable(fn):
        return _extract_id(fn(db))

    from db.models import SessionRow

    row = db.query(SessionRow).first()
    if row is None:
        row = SessionRow(name="Default session")
        db.add(row)
        db.flush()
    return row.id


def _extract_id(obj):
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return obj.get("id") or obj.get("run_id")
    return getattr(obj, "id", None)


def _try_call(fn, db, **kwargs):
    """Call ``fn`` keeping only keyword args it accepts (signature-tolerant)."""
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(db, **kwargs)

    params = sig.parameters
    accepts_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if accepts_kwargs:
        return fn(db, **kwargs)
    allowed = {k: v for k, v in kwargs.items() if k in params}
    return fn(db, **allowed)
