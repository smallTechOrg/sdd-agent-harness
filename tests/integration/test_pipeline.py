"""End-to-end pipeline tests against the REAL LLM (Gemini via AGENT_GEMINI_API_KEY).

Thin smoke coverage of the analyst runner; the exhaustive analytical-shape and
failure-guard coverage lives in ``test_analyst.py``.
"""
import pytest
from sqlalchemy.orm import Session

from graph.runner import run_agent
from db import session as session_module
from db.models import RunRow

_CSV = "region,sales\nNorth,100\nSouth,200\nNorth,150\n"


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_runs_end_to_end(_isolated_db):
    run_id = run_agent(_CSV, "What is the total of the sales column?")
    assert run_id is not None
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.error_message is None
    # Show-its-work invariant: the generated code is persisted.
    assert run.generated_code
    # 100 + 200 + 150 = 450 — the computed total must appear in the answer text
    # (accept a thousands separator the model may add). Strong: it must be 450, not
    # a partial/wrong sum.
    answer = (run.answer or "").lower()
    assert ("450" in answer) or ("{:,}".format(450) in answer), (
        f"expected total 450 in answer; got {run.answer!r}"
    )


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_stores_question(_isolated_db):
    question = "How many rows are in the North region?"
    run_id = run_agent(_CSV, question)
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
    assert run.question == question


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_via_api(api_client):
    """Full HTTP round-trip: POST /runs -> 200 completed with code + table/answer."""
    r = api_client.post(
        "/runs",
        json={"csv_text": _CSV, "question": "What were total sales by region?"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "completed"
    assert data["generated_code"]
    assert data["result_table"] is not None or data["answer"]
    assert not data.get("error")


@pytest.mark.usefixtures("_require_llm_key")
def test_pipeline_error_surfaces_in_api(api_client):
    """A malformed CSV must fail gracefully in the body, never crash."""
    r = api_client.post(
        "/runs",
        json={"csv_text": "a,b,c\n1,2\n3,4,5,6,7\n8", "question": "total of b"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "failed"
    assert data["error"]
