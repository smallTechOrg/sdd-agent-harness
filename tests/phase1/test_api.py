"""API surface tests (Slice C).

Contract tests need no LLM key. The integration test calls REAL Gemini and
skips ONLY if AGENT_GEMINI_API_KEY is unset — a skip BLOCKS the gate.
"""
from pathlib import Path

import pandas as pd
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "employees.csv"
FIXTURE_COLS = ["name", "department", "salary"]


@pytest.fixture(autouse=True)
def _uploads_under_tmp(tmp_path, monkeypatch):
    """Redirect the upload dir into tmp so tests never touch the real data/."""
    import datasets.storage as storage_mod

    monkeypatch.setattr(storage_mod, "UPLOAD_DIR", tmp_path / "uploads")


@pytest.fixture
def _require_gemini():
    from config.settings import get_settings

    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env")


# ---------------------------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------------------------


def test_upload_csv_returns_profile(api_client):
    content = FIXTURE.read_bytes()
    r = api_client.post(
        "/datasets",
        files={"file": ("employees.csv", content, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["error"] is None
    data = r.json()["data"]
    assert data["dataset_id"]
    assert data["filename"] == "employees.csv"
    assert data["file_format"] == "csv"
    assert data["status"] == "ready"
    assert data["row_count"] == 7
    assert data["column_count"] == 3
    assert data["columns"] == FIXTURE_COLS


def test_upload_rejects_non_csv(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_unparseable_csv_is_parse_failed(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("bad.csv", b"\x00\x01\x02\xff\xfe garbage \x00", "text/csv")},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PARSE_FAILED"


def test_get_dataset_details_roundtrip(api_client):
    content = FIXTURE.read_bytes()
    up = api_client.post(
        "/datasets",
        files={"file": ("employees.csv", content, "text/csv")},
    )
    dataset_id = up.json()["data"]["dataset_id"]

    r = api_client.get(f"/datasets/{dataset_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dataset_id"] == dataset_id
    assert data["row_count"] == 7
    assert data["columns"] == FIXTURE_COLS


def test_get_dataset_unknown_is_404(api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# POST /analyses + GET /analyses/{id}
# ---------------------------------------------------------------------------


def test_analyses_unknown_dataset_is_404(api_client):
    r = api_client.post(
        "/analyses",
        json={"dataset_id": "nope", "question": "What is the average salary?"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_analyses_dataset_not_ready_is_409(api_client, _isolated_db):
    from sqlalchemy.orm import Session

    from db.models import DatasetRow

    with Session(_isolated_db) as s:
        ds = DatasetRow(
            filename="pending.csv",
            file_format="csv",
            local_path="",
            status="failed",
        )
        s.add(ds)
        s.commit()
        dataset_id = ds.id

    r = api_client.post(
        "/analyses",
        json={"dataset_id": dataset_id, "question": "What is the average salary?"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "DATASET_NOT_READY"


def test_get_analysis_unknown_is_404(api_client):
    r = api_client.get("/analyses/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Integration — REAL Gemini (skip blocks the gate; key IS set)
# ---------------------------------------------------------------------------


def test_full_upload_then_analyze_real_gemini(api_client, _require_gemini):
    # 1. Upload the fixture.
    up = api_client.post(
        "/datasets",
        files={"file": ("employees.csv", FIXTURE.read_bytes(), "text/csv")},
    )
    assert up.status_code == 200, up.text
    dataset_id = up.json()["data"]["dataset_id"]

    # 2. Ask a question with a known computed answer, against REAL Gemini.
    r = api_client.post(
        "/analyses",
        json={"dataset_id": dataset_id, "question": "What is the average salary?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["status"] == "completed", f"expected completed, got {data!r}"
    assert data["analysis_id"]
    assert data["dataset_id"] == dataset_id
    assert data["attempts"] >= 1

    assert data["answer"] and data["answer"].strip(), "answer must be non-empty"
    assert data["code"] and data["code"].strip(), "code must be non-empty"
    assert "salary" in data["code"], "code must reference the real 'salary' column"
    assert data["steps"] and data["steps"].strip(), "steps must be non-empty"

    # 3. The computed value must MATCH the real pandas mean over the fixture.
    truth = float(pd.read_csv(FIXTURE)["salary"].mean())
    haystack = f"{data['result_value']}\n{data['steps']}\n{data['answer']}"
    assert (
        str(round(truth)) in haystack
        or f"{truth:.2f}" in haystack
        or f"{truth:.1f}" in haystack
        or str(int(truth)) in haystack
    ), f"computed mean {truth} not found in result/steps/answer: {haystack!r}"

    # 4. GET re-fetch returns the same shape.
    got = api_client.get(f"/analyses/{data['analysis_id']}")
    assert got.status_code == 200
    refetched = got.json()["data"]
    assert refetched["analysis_id"] == data["analysis_id"]
    assert refetched["status"] == "completed"
    assert refetched["code"] == data["code"]
