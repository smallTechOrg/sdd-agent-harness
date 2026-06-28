"""Phase-2 dataset-browser gate — GET /datasets and GET /datasets/{id}/runs.

Both endpoints are PURE DB READS (no LLM, no DuckDB execution). The gate uploads
two CSVs, asks a REAL question on each (real Gemini), then asserts the list and
the run history, that a re-opened run renders identically to the live ask, that
re-reading history makes NO LLM call and creates NO new run, and that the data
survives a fresh DB session (restart-survival via SQLite, not memory).
"""
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import session as session_module
from db.models import DatasetRow, QuestionRunRow
from graph.runner import get_dataset_runs, list_datasets

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SALES = _FIXTURES / "sales.csv"
_MESSY = _FIXTURES / "messy.csv"


def _upload(api_client, path: Path) -> dict:
    with path.open("rb") as fh:
        r = api_client.post("/datasets", files={"file": (path.name, fh, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _ask(api_client, dataset_id: str, question: str) -> dict:
    r = api_client.post(f"/datasets/{dataset_id}/ask", json={"question": question})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _run_count(dataset_id: str) -> int:
    """Count persisted runs via a FRESH session (proves persistence, not memory)."""
    with Session(session_module._engine) as s:
        return len(
            s.execute(
                select(QuestionRunRow).where(QuestionRunRow.dataset_id == dataset_id)
            )
            .scalars()
            .all()
        )


@pytest.mark.usefixtures("_require_llm_key")
def test_dataset_browser_end_to_end(api_client):
    """Happy path: two datasets, a real ask on each, then list + history reads."""
    ds_sales = _upload(api_client, _SALES)
    sales_ask = _ask(api_client, ds_sales["id"], "Which region had the highest total sales?")
    assert sales_ask["status"] == "completed", sales_ask.get("error_message")

    ds_messy = _upload(api_client, _MESSY)
    messy_ask = _ask(api_client, ds_messy["id"], "What is the total amount across all orders?")
    assert messy_ask["status"] == "completed", messy_ask.get("error_message")

    # --- GET /datasets: both present, newest-first, correct question_count ---
    r = api_client.get("/datasets")
    assert r.status_code == 200, r.text
    listing = r.json()["data"]
    assert isinstance(listing, list) and len(listing) == 2
    # newest-first: messy was uploaded after sales
    assert listing[0]["id"] == ds_messy["id"]
    assert listing[1]["id"] == ds_sales["id"]
    by_id = {d["id"]: d for d in listing}
    assert by_id[ds_sales["id"]]["name"] == "sales.csv"
    assert by_id[ds_sales["id"]]["row_count"] > 0
    assert by_id[ds_sales["id"]]["status"] == "ready"
    assert by_id[ds_sales["id"]]["question_count"] >= 1
    assert by_id[ds_messy["id"]]["question_count"] >= 1
    # created_at serialized as an ISO string
    assert isinstance(by_id[ds_sales["id"]]["created_at"], str)
    assert "T" in by_id[ds_sales["id"]]["created_at"]

    # --- GET /datasets/{id}/runs: same AskResult shape as the live ask ---
    r = api_client.get(f"/datasets/{ds_sales['id']}/runs")
    assert r.status_code == 200, r.text
    runs = r.json()["data"]
    assert isinstance(runs, list) and len(runs) == 1
    rec = runs[0]
    # carries the two history-only fields
    assert rec["question"] == "Which region had the highest total sales?"
    assert isinstance(rec["created_at"], str) and "T" in rec["created_at"]
    # reconstructed identically to the live ask
    assert rec["run_id"] == sales_ask["run_id"]
    assert rec["status"] == "completed"
    assert rec["answer"] and rec["answer"] == sales_ask["answer"]
    assert rec["sql"] and rec["sql"] == sales_ask["sql"]
    assert rec["trace"] == sales_ask["trace"]
    assert rec["plan"] == sales_ask["plan"]
    assert rec["key_numbers"] == sales_ask["key_numbers"]
    # chart + table reconstructed from the persisted bounded record
    assert rec["chart"] == sales_ask["chart"]
    assert rec["table"] == sales_ask["table"]
    if rec["chart"] is not None and rec["chart"].get("type") != "table":
        assert isinstance(rec["chart"].get("data"), list)

    # --- re-opening history makes NO new run (no LLM re-call) ---
    runs_before = _run_count(ds_sales["id"])
    api_client.get(f"/datasets/{ds_sales['id']}/runs")
    api_client.get(f"/datasets/{ds_sales['id']}/runs")
    runs_after = _run_count(ds_sales["id"])
    assert runs_after == runs_before == 1, "history fetch must not create a run / call the LLM"


@pytest.mark.usefixtures("_require_llm_key")
def test_runs_persist_across_fresh_session(api_client):
    """Restart-survival: the persisted run is readable from a brand-new session
    (the data is in SQLite on disk, not in app memory)."""
    ds = _upload(api_client, _SALES)
    ask = _ask(api_client, ds["id"], "Which region had the highest total sales?")
    assert ask["status"] == "completed", ask.get("error_message")

    # A fresh runner call (new DB session under the hood) sees the same data.
    runs = get_dataset_runs(ds["id"])
    assert runs is not None and len(runs) == 1
    assert runs[0]["run_id"] == ask["run_id"]
    assert runs[0]["answer"] == ask["answer"]

    # And list_datasets sees it with the right count.
    summaries = {d["id"]: d for d in list_datasets()}
    assert summaries[ds["id"]]["question_count"] == 1


def test_get_datasets_empty(api_client):
    """Empty DB → 200 + [] (a valid sidebar state, not an error)."""
    r = api_client.get("/datasets")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_runs_for_missing_dataset_404(api_client):
    r = api_client.get("/datasets/does-not-exist/runs")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_runs_for_dataset_with_no_history_empty(api_client):
    """Existing dataset, no questions yet → 200 + [] (distinct from 404)."""
    ds = _upload(api_client, _SALES)
    r = api_client.get(f"/datasets/{ds['id']}/runs")
    assert r.status_code == 200
    assert r.json()["data"] == []
    # And it appears in the listing with question_count 0.
    listing = api_client.get("/datasets").json()["data"]
    assert listing[0]["id"] == ds["id"]
    assert listing[0]["question_count"] == 0
