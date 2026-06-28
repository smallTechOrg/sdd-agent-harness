"""Browser route contract tests — no LLM (pure DB reads).

Verifies the envelope, ordering, the 404 vs empty-[] distinction, and that the
HTTP routes return what the runner produces. Seeds rows directly so no Gemini
call is needed.
"""
import json
from datetime import datetime, timedelta, timezone

from db.models import DatasetRow, QuestionRunRow
from db.session import create_db_session


def _seed_dataset(ds_id, name, created_at, *, runs=0):
    with create_db_session() as s:
        s.add(
            DatasetRow(
                id=ds_id,
                name=name,
                source_path=f"/tmp/{ds_id}.csv",
                duckdb_path=f"/tmp/{ds_id}.duckdb",
                table_name="t",
                schema_json=json.dumps({"columns": []}),
                profile_json=json.dumps({"row_count": 1, "columns": []}),
                row_count=1,
                status="ready",
                created_at=created_at,
            )
        )
        for i in range(runs):
            s.add(
                QuestionRunRow(
                    id=f"{ds_id}-run-{i}",
                    dataset_id=ds_id,
                    question=f"Q{i}?",
                    status="completed",
                    answer="ok",
                    result_json=json.dumps({"columns": ["a"], "rows": [[1]]}),
                    chart_json=json.dumps({"type": "table"}),
                    trace_json=json.dumps([{"step": "plan", "ok": True}]),
                    created_at=created_at + timedelta(minutes=i + 1),
                )
            )


def test_list_endpoint_envelope_and_order(api_client):
    base = datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc)
    _seed_dataset("a", "a.csv", base, runs=1)
    _seed_dataset("b", "b.csv", base + timedelta(hours=1), runs=3)

    r = api_client.get("/datasets")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    data = body["data"]
    assert [d["id"] for d in data] == ["b", "a"]  # newest first
    assert {d["id"]: d["question_count"] for d in data} == {"a": 1, "b": 3}


def test_list_endpoint_empty(api_client):
    r = api_client.get("/datasets")
    assert r.status_code == 200
    assert r.json() == {"data": [], "error": None}


def test_runs_endpoint_404(api_client):
    r = api_client.get("/datasets/missing/runs")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_runs_endpoint_empty_for_existing_dataset(api_client):
    base = datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc)
    _seed_dataset("solo", "solo.csv", base, runs=0)
    r = api_client.get("/datasets/solo/runs")
    assert r.status_code == 200
    assert r.json() == {"data": [], "error": None}


def test_runs_endpoint_returns_records(api_client):
    base = datetime(2026, 6, 29, 10, 0, 0, tzinfo=timezone.utc)
    _seed_dataset("hist", "hist.csv", base, runs=2)
    r = api_client.get("/datasets/hist/runs")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 2
    # newest-first
    assert data[0]["run_id"] == "hist-run-1"
    rec = data[0]
    assert rec["question"] == "Q1?"
    assert rec["status"] == "completed"
    assert rec["table"] == {"columns": ["a"], "rows": [[1]]}
    assert "created_at" in rec
