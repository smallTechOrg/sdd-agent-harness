"""API contract tests — no LLM key required (graph not invoked)."""
from unittest.mock import patch


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_ask_unknown_dataset_404(api_client):
    r = api_client.post("/datasets/does-not-exist/ask", json={"question": "hi"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_ask_empty_question_400(api_client, _isolated_db):
    from sqlalchemy.orm import Session
    from db.models import DatasetRow
    import json

    with Session(_isolated_db) as s:
        ds = DatasetRow(
            name="x.csv",
            duckdb_path="/tmp/none.duckdb",
            table_name="data",
            schema_json=json.dumps([{"name": "a", "type": "BIGINT"}]),
            row_count=0,
        )
        s.add(ds)
        s.commit()
        ds_id = ds.id

    r = api_client.post(f"/datasets/{ds_id}/ask", json={"question": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_QUESTION"


def test_upload_non_csv_rejected(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_FILE"


def test_upload_empty_csv_rejected(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("empty.csv", b"   ", "text/csv")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_FILE"


def test_ask_contract_shape_with_mocked_runner(api_client, _isolated_db):
    """The ask response always carries the full contract incl. null placeholders."""
    from sqlalchemy.orm import Session
    from db.models import DatasetRow
    import json

    with Session(_isolated_db) as s:
        ds = DatasetRow(
            name="x.csv",
            duckdb_path="/tmp/none.duckdb",
            table_name="data",
            schema_json=json.dumps([{"name": "a", "type": "BIGINT"}]),
            row_count=0,
        )
        s.add(ds)
        s.commit()
        ds_id = ds.id

    fake = {
        "run_id": "run-1",
        "dataset_id": ds_id,
        "status": "completed",
        "question": "q",
        "answer": "The total is 5.",
        "sql": "SELECT sum(a) AS total FROM data;",
        "result": [{"total": 5}],
        "flagged": False,
        "error": None,
        "chart": None,
        "summary_table": None,
        "followups": None,
    }
    with patch("api.datasets.run_analysis", return_value=fake):
        r = api_client.post(f"/datasets/{ds_id}/ask", json={"question": "q"})

    assert r.status_code == 200
    data = r.json()["data"]
    for key in (
        "run_id", "dataset_id", "status", "question", "answer", "sql",
        "result", "flagged", "error", "chart", "summary_table",
        "followups", "tokens",
    ):
        assert key in data, f"missing contract key {key}"
    assert data["chart"] is None
    assert data["summary_table"] is None
    assert data["followups"] is None
    assert data["tokens"] is None
    assert data["answer"] == "The total is 5."
