"""Real-Gemini integration test for `POST /ask` (single-dataset Q&A).

Requires `AGENT_GEMINI_API_KEY` in `.env`. Auto-detect selects the real Gemini
provider (no key is forced to stub here). Drives upload -> ask through the
`api_client` TestClient and asserts on REAL response content: a completed run
with non-stub prose containing a number, plus recorded steps.
"""
import io

import pytest


_NUMERIC_CSV = "value\n10\n20\n30\n40\n50\n"


@pytest.mark.usefixtures("_require_llm_key")
def test_ask_real_gemini_aggregation(api_client):
    files = {"file": ("numbers.csv", io.BytesIO(_NUMERIC_CSV.encode()), "text/csv")}
    up = api_client.post("/upload", files=files)
    assert up.status_code == 200, up.text
    dataset_id = up.json()["data"]["dataset_id"]

    r = api_client.post(
        "/ask",
        json={"dataset_id": dataset_id, "question": "What is the average of the value column?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["type"] == "answer"
    assert data["status"] == "completed"

    answer = data["answer_markdown"]
    assert answer and answer.strip(), "answer_markdown must be non-empty real prose"
    assert "[stub]" not in answer, f"got a stub answer, real provider not used: {answer!r}"
    assert any(ch.isdigit() for ch in answer), f"expected a number in the answer: {answer!r}"

    assert data["answer_html"]
    assert len(data["steps"]) >= 1
    assert data["iteration_count"] >= 1
