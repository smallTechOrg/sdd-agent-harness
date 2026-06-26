"""API contract tests for the analyst `POST /runs {csv_text, question}` shape.

These assert the HTTP envelope and the response field shape WITHOUT calling the
LLM: the graph is replaced with a pre-inserted run via a patched ``run_agent``,
so they are fast and deterministic. The real-Gemini behaviour is covered in
``tests/integration/test_analyst.py``.
"""
import json

from unittest.mock import patch

from sqlalchemy.orm import Session

from db.models import RunRow


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_run_returns_analyst_envelope(api_client, _isolated_db):
    """POST /runs returns the analyst data shape (no transform fields)."""
    result_table = {"columns": ["region", "sales"], "rows": [["North", 520]]}
    with Session(_isolated_db) as s:
        row = RunRow(
            status="completed",
            question="total sales by region",
            answer="North: 520",
            explanation="Grouped by region and summed sales.",
            generated_code="result = df.groupby('region')['sales'].sum().reset_index()",
            result_table=json.dumps(result_table),
        )
        s.add(row)
        s.commit()
        run_id = row.id

    with patch("api.runs.run_agent", return_value=run_id):
        r = api_client.post(
            "/runs",
            json={"csv_text": "region,sales\nNorth,520", "question": "total sales by region"},
        )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["run_id"] == run_id
    assert data["status"] == "completed"
    assert data["answer"] == "North: 520"
    assert data["explanation"]
    assert "groupby" in data["generated_code"]
    assert data["result_table"] == result_table
    assert data["truncated"] is False
    assert data["error"] is None
    # The legacy transform fields are gone.
    assert "input_text" not in data
    assert "output_text" not in data


def test_run_failed_status_surfaces_error(api_client, _isolated_db):
    """A handled failure is HTTP 200 with status=failed and error set."""
    with Session(_isolated_db) as s:
        row = RunRow(
            status="failed",
            question="bad input",
            error_message="Couldn't read that as a CSV — it is malformed.",
        )
        s.add(row)
        s.commit()
        run_id = row.id

    with patch("api.runs.run_agent", return_value=run_id):
        r = api_client.post("/runs", json={"csv_text": "@@@", "question": "bad input"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "failed"
    assert data["error"]
    assert "CSV" in data["error"]


def test_run_missing_csv_text_is_422(api_client):
    r = api_client.post("/runs", json={"question": "total sales"})
    assert r.status_code == 422


def test_run_missing_question_is_422(api_client):
    r = api_client.post("/runs", json={"csv_text": "region,sales\nNorth,1"})
    assert r.status_code == 422


def test_run_empty_body_is_422(api_client):
    r = api_client.post("/runs", json={})
    assert r.status_code == 422


def test_get_run_not_found(api_client):
    r = api_client.get("/runs/nonexistent-id")
    assert r.status_code == 404
