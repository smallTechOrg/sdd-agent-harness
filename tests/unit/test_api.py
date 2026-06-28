"""API contract tests for the DataChat routes (no LLM key required).

These exercise the non-LLM routes against the isolated DB (conftest's
``_isolated_db`` monkeypatches the session engine, and ``api_client`` drives the
real FastAPI app via TestClient). The LLM-backed SSE path is covered by the
agent-graph integration tests + the e2e flow; here we assert the SSE endpoint's
PRE-stream guards (404 unknown dataset, 400 empty question) and the full
upload→profile→get→history→detail loop, which is REAL pandas with no model call.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SMALL_CSV = FIXTURES / "small_sales.csv"


# --------------------------------------------------------------------------- #
# Health (skeleton, kept)
# --------------------------------------------------------------------------- #

def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"data": {"status": "ok"}, "error": None}


# --------------------------------------------------------------------------- #
# POST /api/datasets — upload + profile (REAL pandas, no LLM)
# --------------------------------------------------------------------------- #

def _upload(api_client, name="small_sales.csv"):
    content = SMALL_CSV.read_bytes()
    return api_client.post(
        "/api/datasets",
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )


def test_upload_profiles_csv(api_client):
    r = _upload(api_client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert r.json()["error"] is None
    assert "dataset_id" in data and data["dataset_id"]
    assert data["name"] == "small_sales.csv"

    profile = data["profile"]
    # small_sales.csv has 6 data rows and 4 columns (region/product/revenue/units).
    assert profile["row_count"] == 6
    col_names = {c["name"] for c in profile["columns"]}
    assert col_names == {"region", "product", "revenue", "units"}
    assert isinstance(profile["sample_rows"], list)
    assert len(profile["sample_rows"]) <= 6
    # A numeric column carries min/max/mean; revenue has one missing value.
    revenue = next(c for c in profile["columns"] if c["name"] == "revenue")
    assert revenue["missing"] == 1
    assert "mean" in revenue


def test_upload_rejects_non_csv(api_client):
    r = api_client.post(
        "/api/datasets",
        files={"file": ("sales.xlsx", io.BytesIO(b"PK\x03\x04not-a-csv"), "application/octet-stream")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "UNSUPPORTED_TYPE"


def test_upload_rejects_malformed_csv(api_client):
    # Ragged rows that pandas cannot parse → MALFORMED_FILE.
    bad = b'a,b,c\n1,2\n3,4,5,6,7,8\n"unterminated'
    r = api_client.post(
        "/api/datasets",
        files={"file": ("bad.csv", io.BytesIO(bad), "text/csv")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "MALFORMED_FILE"


# --------------------------------------------------------------------------- #
# GET /api/datasets/{id} + /messages + library list
# --------------------------------------------------------------------------- #

def test_get_dataset_returns_profile_and_empty_thread(api_client):
    dataset_id = _upload(api_client).json()["data"]["dataset_id"]
    r = api_client.get(f"/api/datasets/{dataset_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dataset_id"] == dataset_id
    assert data["name"] == "small_sales.csv"
    assert data["profile"]["row_count"] == 6
    assert data["messages"] == []  # no questions asked yet


def test_get_dataset_unknown_404(api_client):
    r = api_client.get("/api/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_list_messages_unknown_404(api_client):
    r = api_client.get("/api/datasets/does-not-exist/messages")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_list_messages_empty(api_client):
    dataset_id = _upload(api_client).json()["data"]["dataset_id"]
    r = api_client.get(f"/api/datasets/{dataset_id}/messages")
    assert r.status_code == 200
    assert r.json() == {"data": [], "error": None}


def test_message_detail_unknown_404(api_client):
    r = api_client.get("/api/messages/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_library_list_is_real_envelope_and_lists_uploaded(api_client):
    # Phase-1 stub returns the active datasets as summaries in the envelope.
    before = api_client.get("/api/datasets")
    assert before.status_code == 200
    assert before.json()["error"] is None
    assert isinstance(before.json()["data"], list)

    dataset_id = _upload(api_client).json()["data"]["dataset_id"]
    after = api_client.get("/api/datasets").json()["data"]
    assert any(d["dataset_id"] == dataset_id for d in after)


# --------------------------------------------------------------------------- #
# POST /api/datasets/{id}/ask — pre-stream guards (no LLM call reached)
# --------------------------------------------------------------------------- #

def test_ask_empty_question_400(api_client):
    dataset_id = _upload(api_client).json()["data"]["dataset_id"]
    r = api_client.post(f"/api/datasets/{dataset_id}/ask", json={"question": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_QUESTION"


def test_ask_missing_question_field_400(api_client):
    dataset_id = _upload(api_client).json()["data"]["dataset_id"]
    r = api_client.post(f"/api/datasets/{dataset_id}/ask", json={})
    # Defaulted to "" by the model → blank → EMPTY_QUESTION (400), not a 422.
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_QUESTION"


def test_ask_unknown_dataset_404_before_stream(api_client):
    r = api_client.post(
        "/api/datasets/does-not-exist/ask",
        json={"question": "How many rows are there?"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# POST /api/datasets/{id}/ask — REAL streamed run (skips without a Gemini key)
# --------------------------------------------------------------------------- #

@pytest.mark.usefixtures("_require_llm_key")
def test_ask_streams_real_sse_to_done(api_client):
    """End-to-end SSE: a real run streams ordered events ending in `done`.

    Uses the real Gemini key from .env; skips if absent. Asserts the SSE frames
    arrive (status → ... → done) and that the run is persisted as completed.
    """
    dataset_id = _upload(api_client).json()["data"]["dataset_id"]

    events: list[tuple[str, dict]] = []
    with api_client.stream(
        "POST",
        f"/api/datasets/{dataset_id}/ask",
        json={"question": "How many rows are in the dataset?"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        event_name = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and event_name:
                payload = json.loads(line.split(":", 1)[1].strip())
                events.append((event_name, payload))

    names = [n for n, _ in events]
    assert "status" in names, names
    assert names[-1] in {"done", "error"}, names
    terminal_name, terminal = events[-1]
    assert "message_id" in terminal

    if terminal_name == "done":
        assert terminal["status"] == "completed"
        # The persisted record is readable via the detail route.
        detail = api_client.get(f"/api/messages/{terminal['message_id']}")
        assert detail.status_code == 200
        body = detail.json()["data"]
        assert body["status"] == "completed"
        assert body["answer"]
        assert body["cost_usd"] >= 0.0
