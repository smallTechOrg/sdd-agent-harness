"""Unit tests for the dataset-browser runner shaping — no LLM, no DuckDB.

These build DB rows directly and assert ``list_datasets`` / ``get_dataset_runs``
shape them into the documented contract. Covers ordering, the grouped COUNT,
chart/table reconstruction from the persisted bounded record, the failed-run
body, the missing-dataset (None → 404) case, and the empty-history case.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from db.models import DatasetRow, QuestionRunRow
from db.session import create_db_session
from graph.runner import get_dataset_runs, list_datasets


def _make_dataset(session, ds_id: str, name: str, created_at: datetime) -> DatasetRow:
    row = DatasetRow(
        id=ds_id,
        name=name,
        source_path=f"/tmp/{ds_id}.csv",
        duckdb_path=f"/tmp/{ds_id}.duckdb",
        table_name="t",
        schema_json=json.dumps({"columns": []}),
        profile_json=json.dumps({"row_count": 3, "columns": []}),
        row_count=3,
        status="ready",
        created_at=created_at,
    )
    session.add(row)
    return row


def _make_run(session, run_id, ds_id, question, created_at, **over):
    defaults = dict(
        plan="Sum sales by region.",
        sql="SELECT region, SUM(sales) AS total FROM t GROUP BY region",
        trace_json=json.dumps([{"step": "plan", "ok": True}, {"step": "execute", "ok": True}]),
        result_json=json.dumps(
            {"columns": ["region", "total"], "rows": [["West", 4200], ["East", 3100]]}
        ),
        chart_json=json.dumps({"type": "bar", "x": "region", "y": "total"}),
        answer="The West region had the highest total.",
        key_numbers_json=json.dumps([{"label": "West total", "value": "4200"}]),
        cost_usd=0.0021,
        status="completed",
        error_message=None,
    )
    defaults.update(over)
    run = QuestionRunRow(
        id=run_id, dataset_id=ds_id, question=question, created_at=created_at, **defaults
    )
    session.add(run)
    return run


@pytest.fixture
def _seed():
    base = datetime(2026, 6, 29, 12, 0, 0, tzinfo=timezone.utc)
    with create_db_session() as s:
        _make_dataset(s, "ds-old", "sales.csv", base)
        _make_dataset(s, "ds-new", "headcount.csv", base + timedelta(hours=2))
        # ds-old has two runs (older + newer), ds-new has none.
        _make_run(s, "run-1", "ds-old", "Q1?", base + timedelta(minutes=10))
        _make_run(s, "run-2", "ds-old", "Q2?", base + timedelta(minutes=20))
    return base


def test_list_datasets_newest_first_with_counts(_seed):
    out = list_datasets()
    assert [d["id"] for d in out] == ["ds-new", "ds-old"]
    by_id = {d["id"]: d for d in out}
    assert by_id["ds-old"]["question_count"] == 2
    assert by_id["ds-new"]["question_count"] == 0
    assert by_id["ds-old"]["name"] == "sales.csv"
    assert by_id["ds-old"]["row_count"] == 3
    assert by_id["ds-old"]["status"] == "ready"
    assert isinstance(by_id["ds-old"]["created_at"], str)


def test_list_datasets_empty():
    assert list_datasets() == []


def test_get_dataset_runs_reconstructs_chart_and_table(_seed):
    runs = get_dataset_runs("ds-old")
    assert runs is not None and len(runs) == 2
    # newest-first
    assert [r["run_id"] for r in runs] == ["run-2", "run-1"]
    rec = runs[0]
    assert rec["question"] == "Q2?"
    assert rec["status"] == "completed"
    assert rec["answer"] == "The West region had the highest total."
    assert rec["key_numbers"] == [{"label": "West total", "value": "4200"}]
    # table reconstructed from result_json
    assert rec["table"] == {
        "columns": ["region", "total"],
        "rows": [["West", 4200], ["East", 3100]],
    }
    # chart.data rebuilt by zipping x/y against the bounded rows (same _chart_data)
    assert rec["chart"]["type"] == "bar"
    assert rec["chart"]["data"] == [
        {"region": "West", "total": 4200},
        {"region": "East", "total": 3100},
    ]
    assert isinstance(rec["created_at"], str)


def test_get_dataset_runs_missing_dataset_returns_none(_seed):
    assert get_dataset_runs("nope") is None


def test_get_dataset_runs_empty_history(_seed):
    assert get_dataset_runs("ds-new") == []


def test_failed_run_record_body(_seed):
    with create_db_session() as s:
        _make_run(
            s,
            "run-fail",
            "ds-new",
            "broken?",
            datetime(2026, 6, 29, 13, 0, 0, tzinfo=timezone.utc),
            status="failed",
            answer=None,
            result_json=None,
            chart_json=None,
            key_numbers_json=None,
            error_message="SQL uncorrectable after retries",
        )
    runs = get_dataset_runs("ds-new")
    assert len(runs) == 1
    rec = runs[0]
    assert rec["status"] == "failed"
    assert rec["answer"] is None
    assert rec["chart"] is None
    assert rec["table"] is None
    assert rec["key_numbers"] == []
    assert rec["error_message"] == "SQL uncorrectable after retries"
    # trace still present so a failed run can be re-opened to see what was tried
    assert rec["trace"]


def test_table_only_chart_not_rebuilt(_seed):
    """A 'table' chart type keeps no rebuilt data series (mirrors live _ask_payload)."""
    with create_db_session() as s:
        _make_run(
            s,
            "run-tbl",
            "ds-new",
            "list?",
            datetime(2026, 6, 29, 13, 30, 0, tzinfo=timezone.utc),
            chart_json=json.dumps({"type": "table"}),
        )
    rec = get_dataset_runs("ds-new")[0]
    assert rec["chart"] == {"type": "table"}
    assert "data" not in rec["chart"]
