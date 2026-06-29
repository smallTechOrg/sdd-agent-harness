"""Analysis runner: loads a dataset, runs the graph, persists the Run."""
from __future__ import annotations

import json
import time

from graph.agent import agentic_ai
from graph.state import AgentState
from db.session import create_db_session
from db.models import RunRow, DatasetRow
from observability.events import get_logger

log = get_logger("runner")


class DatasetNotFound(Exception):
    """Raised when the dataset id does not exist."""


def run_analysis(dataset_id: str, question: str) -> dict:
    """Run the analysis graph for ``question`` against ``dataset_id``.

    Returns a dict shaped for the API ask-endpoint contract:
    ``{run_id, dataset_id, status, question, answer, sql, result, flagged, error}``.
    Raises ``DatasetNotFound`` if the dataset id is unknown.
    """
    # Load dataset (schema + duckdb path).
    with create_db_session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        if dataset is None:
            raise DatasetNotFound(dataset_id)
        schema = json.loads(dataset.schema_json)
        dataset_path = dataset.duckdb_path

    # Create the pending Run row up front (audit trail).
    with create_db_session() as session:
        run = RunRow(
            status="pending",
            dataset_id=dataset_id,
            question=question,
            input_text=question,
        )
        session.add(run)
        session.flush()
        run_id = run.id

    log.info("run.start", run_id=run_id, dataset_id=dataset_id)
    started = time.monotonic()

    initial: AgentState = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "dataset_path": dataset_path,
        "schema": schema,
        "question": question,
        "sql": None,
        "sql_error": None,
        "sql_attempts": 0,
        "result_rows": None,
        "error": None,
        "flagged": False,
        "chart": None,
        "summary_table": None,
        "followups": None,
    }

    final = agentic_ai.invoke(initial)

    status = final.get("status", "failed")
    sql = final.get("sql")
    result_rows = final.get("result_rows")
    answer_text = final.get("answer_text")
    output_text = final.get("output_text")
    error = final.get("error") or final.get("sql_error")
    flagged = bool(final.get("flagged", False))
    chart = final.get("chart")
    summary_table = final.get("summary_table")
    followups = final.get("followups")
    duration_ms = int((time.monotonic() - started) * 1000)

    # On failure we never surface a fabricated number or fabricated enrichment.
    if status != "completed":
        answer_text = None
        result_rows = None
        chart = None
        summary_table = None
        followups = None

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.status = status
        run.sql = sql
        run.result_json = json.dumps(result_rows) if result_rows is not None else None
        run.output_text = output_text if status == "completed" else None
        run.error_message = error if status != "completed" else None
        run.tokens_json = None  # Phase 1: token capture deferred (Phase 3).

    log.info(
        "run.end",
        run_id=run_id,
        status=status,
        duration_ms=duration_ms,
        error=error if status != "completed" else None,
    )

    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "status": status,
        "question": question,
        "answer": answer_text,
        "sql": sql if status == "completed" else None,
        "result": result_rows,
        "flagged": flagged,
        "error": error if status != "completed" else None,
        "chart": chart,
        "summary_table": summary_table,
        "followups": followups,
    }
