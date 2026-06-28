"""Runner: bridges the API <-> the graph <-> the DB.

* ``ingest_dataset`` — ingest+profile a CSV into a local DuckDB file and create
  the ``DatasetRow`` (no LLM call). Returns the profile payload.
* ``run_question`` — create the ``QuestionRunRow``, invoke the graph with the
  dataset's DuckDB path + schema, persist plan/sql/trace/result/chart/answer/
  key_numbers/cost/status, and return the API ``ask`` payload.
"""
import json
import time
from pathlib import Path
from uuid import uuid4

from analysis import extract_schema, ingest_csv, profile_dataset
from db.models import DatasetRow, QuestionRunRow
from db.session import create_db_session
from graph.agent import agentic_ai
from graph.state import AnalystState
from observability.events import log_run_outcome

# Repo-root-relative data dirs (src/graph/runner.py -> 2 parents up = repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DUCKDB_DIR = _REPO_ROOT / "data" / "duckdb"
_UPLOADS_DIR = _REPO_ROOT / "data" / "uploads"

_TABLE_NAME = "t"


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _dataset_payload(row: DatasetRow) -> dict:
    """The shared profile payload shape for POST/GET /datasets."""
    schema = json.loads(row.schema_json)
    profile = json.loads(row.profile_json)
    return {
        "id": row.id,
        "name": row.name,
        "row_count": row.row_count,
        "columns": schema.get("columns", []),
        "profile": profile,
        "status": row.status,
    }


def ingest_dataset(filename: str, file_bytes: bytes) -> dict:
    """Save the upload, ingest into a per-dataset DuckDB file, profile it, and
    create the ``DatasetRow``. Returns the profile payload.

    Raises ``RuntimeError`` on DuckDB ingest failure (the API maps it to
    INGEST_FAILED).
    """
    dataset_id = str(uuid4())
    upload_dir = _UPLOADS_DIR / dataset_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    source_path = upload_dir / filename
    source_path.write_bytes(file_bytes)

    _DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    duckdb_path = _DUCKDB_DIR / f"{dataset_id}.duckdb"

    # Ingest + profile (raises RuntimeError on DuckDB error).
    ingest_csv(str(source_path), str(duckdb_path), table_name=_TABLE_NAME)
    schema = extract_schema(str(duckdb_path), table_name=_TABLE_NAME)
    profile = profile_dataset(str(duckdb_path), table_name=_TABLE_NAME)
    row_count = int(profile.get("row_count", 0))

    with create_db_session() as session:
        row = DatasetRow(
            id=dataset_id,
            name=filename,
            source_path=str(source_path),
            duckdb_path=str(duckdb_path),
            table_name=_TABLE_NAME,
            schema_json=json.dumps(schema),
            profile_json=json.dumps(profile),
            row_count=row_count,
            status="ready",
        )
        session.add(row)
        session.flush()
        return _dataset_payload(row)


def get_dataset_payload(dataset_id: str) -> dict | None:
    """Return the profile payload for a dataset, or None if missing."""
    with create_db_session() as session:
        row = session.get(DatasetRow, dataset_id)
        if row is None:
            return None
        return _dataset_payload(row)


def _iso(dt) -> str | None:
    """Serialize a datetime to an ISO-8601 string (None-safe)."""
    return dt.isoformat() if dt is not None else None


def list_datasets() -> list[dict]:
    """List all datasets newest-first with a per-dataset run COUNT.

    Pure DB read (no LLM, no DuckDB). Returns lightweight summaries for the
    sidebar — NOT the full profile. ``question_count`` is computed via a single
    grouped COUNT (no N+1). Empty DB → ``[]``.
    """
    from sqlalchemy import func, select

    with create_db_session() as session:
        # One grouped COUNT of question_runs per dataset (no N+1).
        counts = dict(
            session.execute(
                select(QuestionRunRow.dataset_id, func.count(QuestionRunRow.id)).group_by(
                    QuestionRunRow.dataset_id
                )
            ).all()
        )
        rows = (
            session.execute(
                select(DatasetRow).order_by(DatasetRow.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "name": r.name,
                "row_count": r.row_count,
                "status": r.status,
                "question_count": int(counts.get(r.id, 0)),
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]


def _run_record(run: QuestionRunRow) -> dict:
    """Reconstruct one persisted run into the live ``AskResult`` shape.

    Rebuilds ``chart.data`` and ``table`` from the bounded ``result_json`` using
    the SAME ``_chart_data`` logic the live ``_ask_payload`` uses, so a re-opened
    run renders pixel-identically through the existing ``AnswerPanel``. PURE DB
    read — no LLM call, no DuckDB execution; ``result_json`` is the bounded,
    privacy-safe summary the ``privacy_guard`` already produced.
    """
    result = json.loads(run.result_json) if run.result_json else None
    chart_spec = json.loads(run.chart_json) if run.chart_json else None
    trace = json.loads(run.trace_json) if run.trace_json else []
    key_numbers = json.loads(run.key_numbers_json) if run.key_numbers_json else []

    table = None
    if result:
        table = {"columns": result.get("columns", []), "rows": result.get("rows", [])}

    chart = chart_spec
    if (
        run.status == "completed"
        and chart_spec
        and chart_spec.get("type") != "table"
        and result
    ):
        chart = {**chart_spec, "data": _chart_data(chart_spec, result)}

    if run.status != "completed":
        # Mirror the live failed-ask body: answer/chart/table null, error set,
        # trace still present so the user can see what was tried.
        return {
            "run_id": run.id,
            "status": run.status,
            "question": run.question,
            "answer": None,
            "key_numbers": [],
            "chart": None,
            "table": None,
            "plan": run.plan,
            "sql": run.sql,
            "trace": trace,
            "cost_usd": float(run.cost_usd or 0.0),
            "error_message": run.error_message,
            "created_at": _iso(run.created_at),
        }

    return {
        "run_id": run.id,
        "status": run.status,
        "question": run.question,
        "answer": run.answer,
        "key_numbers": key_numbers,
        "chart": chart,
        "table": table,
        "plan": run.plan,
        "sql": run.sql,
        "trace": trace,
        "cost_usd": float(run.cost_usd or 0.0),
        "error_message": run.error_message,
        "created_at": _iso(run.created_at),
    }


def get_dataset_runs(dataset_id: str) -> list[dict] | None:
    """Run history for a dataset, newest-first, each in the live ``AskResult`` shape.

    Returns ``None`` if the dataset does not exist (router → 404). An existing
    dataset with no runs returns ``[]``. PURE DB read — NO LLM call, NO DuckDB
    execution; re-opening history never sends anything to the model.
    """
    from sqlalchemy import select

    with create_db_session() as session:
        if session.get(DatasetRow, dataset_id) is None:
            return None
        runs = (
            session.execute(
                select(QuestionRunRow)
                .where(QuestionRunRow.dataset_id == dataset_id)
                .order_by(QuestionRunRow.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [_run_record(run) for run in runs]


def _ask_payload(run_id: str, dataset_id: str, final: AnalystState) -> dict:
    """Shape the graph result into the POST /datasets/{id}/ask response data."""
    status = final.get("status", "completed")
    result = final.get("result") or {}
    chart = final.get("chart")
    table = None
    if result:
        table = {"columns": result.get("columns", []), "rows": result.get("rows", [])}

    if status == "completed":
        chart_with_data = None
        if chart and chart.get("type") != "table" and result:
            chart_with_data = {**chart, "data": _chart_data(chart, result)}
        return {
            "run_id": run_id,
            "status": "completed",
            "answer": final.get("answer"),
            "key_numbers": final.get("key_numbers") or [],
            "chart": chart_with_data or chart,
            "table": table,
            "plan": final.get("plan"),
            "sql": final.get("sql"),
            "trace": final.get("trace") or [],
            "cost_usd": float(final.get("cost_usd") or 0.0),
        }
    # failed
    return {
        "run_id": run_id,
        "status": "failed",
        "answer": None,
        "key_numbers": [],
        "chart": None,
        "table": None,
        "plan": final.get("plan"),
        "sql": final.get("sql"),
        "trace": final.get("trace") or [],
        "cost_usd": float(final.get("cost_usd") or 0.0),
        "error_message": final.get("error"),
    }


def _chart_data(chart: dict, result: dict) -> list:
    """Build row-of-dicts chart data from the bounded result for the x/y columns."""
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    x, y = chart.get("x"), chart.get("y")
    if x not in columns or y not in columns:
        return []
    xi, yi = columns.index(x), columns.index(y)
    return [{x: r[xi], y: r[yi]} for r in rows]


def run_question(dataset_id: str, question: str) -> dict | None:
    """Run the agent over a dataset and persist the audit record.

    Returns the API ``ask`` payload, or None if the dataset does not exist.
    """
    started = _now_ms()
    run_id = str(uuid4())

    with create_db_session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        if dataset is None:
            return None
        schema = json.loads(dataset.schema_json)
        dataset_path = dataset.duckdb_path
        table_name = dataset.table_name
        # Persist the run as in-flight up front so failures still leave a record.
        run = QuestionRunRow(
            id=run_id,
            dataset_id=dataset_id,
            question=question,
            status="completed",
        )
        session.add(run)
        session.flush()

    initial: AnalystState = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "question": question,
        "schema": schema,
        "dataset_path": dataset_path,
        "table_name": table_name,
        "sql_attempts": 0,
        "sql_error": None,
        "error": None,
        "trace": [],
        "cost_usd": 0.0,
    }
    final: AnalystState = agentic_ai.invoke(initial)

    payload = _ask_payload(run_id, dataset_id, final)

    # Persist the finalized audit record.
    result = final.get("result") or {}
    bounded_table = (
        {"columns": result.get("columns", []), "rows": result.get("rows", [])[:200]}
        if result
        else None
    )
    with create_db_session() as session:
        run = session.get(QuestionRunRow, run_id)
        run.plan = final.get("plan")
        run.sql = final.get("sql")
        run.trace_json = json.dumps(final.get("trace") or [], default=str)
        run.result_json = json.dumps(bounded_table, default=str) if bounded_table else None
        run.chart_json = (
            json.dumps(final.get("chart"), default=str) if final.get("chart") else None
        )
        run.answer = final.get("answer")
        run.key_numbers_json = json.dumps(final.get("key_numbers") or [], default=str)
        run.cost_usd = float(final.get("cost_usd") or 0.0)
        run.status = final.get("status", "completed")
        run.error_message = final.get("error") if final.get("status") == "failed" else None

    log_run_outcome(
        run_id=run_id,
        dataset_id=dataset_id,
        status=final.get("status", "completed"),
        duration_ms=_now_ms() - started,
        cost_usd=float(final.get("cost_usd") or 0.0),
        error=final.get("error") if final.get("status") == "failed" else None,
    )
    return payload
