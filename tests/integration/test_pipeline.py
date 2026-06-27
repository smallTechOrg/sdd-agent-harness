"""Integration tests for the runner + API surface (NL -> SQL capability).

Require a real LLM key (Gemini) and the seeded DuckDB `sales` table (provided by
the autouse fixture in tests/integration/conftest.py).
"""
import json

import pytest
from sqlalchemy.orm import Session

from graph.runner import run_agent
from db import session as session_module
from db.models import RunRow


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_runs_end_to_end(_isolated_db):
    run_id = run_agent("What were total sales by region?")
    assert run_id is not None
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
    assert run is not None
    assert run.status == "completed"
    # output_text is the JSON analysis payload.
    payload = json.loads(run.output_text)
    assert payload["sql"]
    assert payload["columns"]
    assert payload["rows"]
    assert payload["error"] is None


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_stores_input(_isolated_db):
    input_text = "How many orders are there in total?"
    run_id = run_agent(input_text)
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
    assert run.input_text == input_text


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_via_api(api_client):
    """Full HTTP round-trip: POST /runs -> 200 with a JSON output_text payload."""
    r = api_client.post("/runs", json={"input_text": "Total sales by product?"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "completed"
    payload = json.loads(body["data"]["output_text"])
    assert payload["sql"]
    assert not body["data"].get("error")


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_error_surfaces_in_api(api_client):
    """A run must always surface a consistent JSON payload (output_text), never crash."""
    r = api_client.post("/runs", json={"input_text": "x"})
    assert r.status_code == 200
    body = r.json()
    # output_text is always present and JSON-decodable (success or graceful failure).
    payload = json.loads(body["data"]["output_text"])
    assert "error" in payload
