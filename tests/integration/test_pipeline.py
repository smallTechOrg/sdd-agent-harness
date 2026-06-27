"""Integration tests — Phase 1 data analysis pipeline."""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.usefixtures("_require_llm_key")
def test_upload_and_analyze_bar_chart(api_client):
    """Upload sales CSV, ask bar chart question, assert chart data returned."""
    # Upload
    with open(FIXTURES / "sales.csv", "rb") as f:
        resp = api_client.post("/datasets", files={"file": ("sales.csv", f, "text/csv")})
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    dataset_id = resp.json()["data"]["dataset_id"]
    assert dataset_id
    assert resp.json()["data"]["row_count"] == 25
    columns = resp.json()["data"]["columns"]
    assert "month" in columns and "revenue" in columns

    # Analyze
    resp = api_client.post("/analyze", json={
        "dataset_id": dataset_id,
        "question": "Show me total revenue by month as a bar chart",
    })
    assert resp.status_code == 200, f"Analyze failed: {resp.text}"
    data = resp.json()["data"]
    assert data["chart_type"] in {"bar", "line", "scatter"}
    assert isinstance(data["labels"], list) and len(data["labels"]) >= 3
    assert isinstance(data["values"], list) and len(data["values"]) >= 3
    assert len(data["labels"]) == len(data["values"])
    assert isinstance(data["summary"], str) and len(data["summary"]) > 10


@pytest.mark.usefixtures("_require_llm_key")
def test_analyze_line_chart_trends(api_client):
    """Ask a trends question — should return line chart."""
    with open(FIXTURES / "sales.csv", "rb") as f:
        resp = api_client.post("/datasets", files={"file": ("sales.csv", f, "text/csv")})
    dataset_id = resp.json()["data"]["dataset_id"]

    resp = api_client.post("/analyze", json={
        "dataset_id": dataset_id,
        "question": "Show me the trend of total revenue over the months",
    })
    assert resp.status_code == 200, f"Analyze failed: {resp.text}"
    data = resp.json()["data"]
    # chart_type should be line or bar for trend questions
    assert data["chart_type"] in {"bar", "line", "scatter"}
    assert len(data["labels"]) == len(data["values"])
    assert len(data["labels"]) > 0


def test_upload_invalid_file_type(api_client):
    """Non-CSV/Excel file must return 422."""
    resp = api_client.post("/datasets", files={"file": ("report.txt", b"hello", "text/plain")})
    assert resp.status_code == 422


@pytest.mark.usefixtures("_require_llm_key")
def test_analyze_unknown_dataset(api_client):
    """Unknown dataset_id must return 500."""
    resp = api_client.post("/analyze", json={
        "dataset_id": "00000000-0000-0000-0000-000000000000",
        "question": "Show me revenue by month",
    })
    assert resp.status_code == 500


def test_list_datasets(api_client):
    """GET /datasets returns list (may be empty)."""
    resp = api_client.get("/datasets")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
