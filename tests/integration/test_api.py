"""Integration tests for the DataChat API slice (backend-api).

Drives the real FastAPI app via TestClient against the isolated DB from
conftest (`_isolated_db` autouse fixture creates the datasets/conversations/
messages tables). The /chat test hits the REAL Gemini API via the key in .env
(skips only if genuinely absent) — it is the gate, never stubbed.
"""
import io

import pytest


def _make_sales_csv() -> bytes:
    """A small mixed-type CSV with a clear group-by answer (sales by region)."""
    rows = [
        "region,sales,channel",
        "West,1200,online",
        "East,900,online",
        "North,700,online",
        "South,500,online",
        "West,300,retail",
        "East,100,retail",
        "North,200,retail",
        "South,150,retail",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def _upload_csv(api_client, content: bytes, filename: str = "sales.csv"):
    return api_client.post(
        "/datasets",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )


# --- Upload + schema profiling (no LLM) ------------------------------------


def test_upload_returns_schema_and_row_count(api_client):
    r = _upload_csv(api_client, _make_sales_csv())
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert r.json()["error"] is None

    assert data["dataset_id"]
    assert data["filename"] == "sales.csv"
    assert data["file_type"] == "csv"
    assert data["row_count"] == 8

    cols = {c["name"]: c["dtype"] for c in data["schema"]["columns"]}
    assert cols == {"region": "string", "sales": "number", "channel": "string"}


def test_get_dataset_round_trips_schema(api_client):
    dataset_id = _upload_csv(api_client, _make_sales_csv()).json()["data"]["dataset_id"]

    r = api_client.get(f"/datasets/{dataset_id}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dataset_id"] == dataset_id
    assert data["row_count"] == 8
    names = {c["name"] for c in data["schema"]["columns"]}
    assert names == {"region", "sales", "channel"}


def test_get_unknown_dataset_404(api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_upload_unsupported_type_400_bad_upload(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_UPLOAD"


def test_upload_empty_file_400_bad_upload(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_UPLOAD"


# --- Chat error paths (no LLM needed) --------------------------------------


def test_chat_unknown_dataset_404(api_client):
    r = api_client.post(
        "/chat",
        json={"dataset_id": "nope", "question": "total sales by region?"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_chat_empty_question_400(api_client):
    dataset_id = _upload_csv(api_client, _make_sales_csv()).json()["data"]["dataset_id"]
    r = api_client.post(
        "/chat",
        json={"dataset_id": dataset_id, "question": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_unknown_conversation_404(api_client):
    r = api_client.get("/conversations/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# --- Full chat flow against the REAL Gemini API ----------------------------


@pytest.mark.usefixtures("_require_llm_key")
def test_chat_comparison_returns_answer_and_chart(api_client):
    dataset_id = _upload_csv(api_client, _make_sales_csv()).json()["data"]["dataset_id"]

    r = api_client.post(
        "/chat",
        json={"dataset_id": dataset_id, "question": "What were total sales by region?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    conversation_id = data["conversation_id"]
    assert conversation_id
    assert isinstance(data["answer"], str) and data["answer"].strip()

    # A comparison-across-categories question should yield a chart.
    chart = data["chart"]
    assert chart is not None, "expected a chart for a by-region comparison"
    assert chart["type"] in {"bar", "line", "pie"}
    assert len(chart["labels"]) == len(chart["series"][0]["values"])
    assert len(chart["labels"]) >= 1

    # The conversation now restores via GET, with user+assistant messages persisted.
    cr = api_client.get(f"/conversations/{conversation_id}")
    assert cr.status_code == 200, cr.text
    conv = cr.json()["data"]
    assert conv["conversation_id"] == conversation_id
    assert conv["dataset_id"] == dataset_id

    roles = [m["role"] for m in conv["messages"]]
    assert "user" in roles and "assistant" in roles
    user_msg = next(m for m in conv["messages"] if m["role"] == "user")
    assert "region" in user_msg["content"].lower()
