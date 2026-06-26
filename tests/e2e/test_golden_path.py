"""Real-Gemini golden-path E2E through the FastAPI TestClient.

The full single-dataset journey a Phase-2 user takes: health (provider banner) ->
upload -> datasets list -> ask -> a real answer with content -> runs/current shows
the completed run. Requires `AGENT_GEMINI_API_KEY` in `.env`; auto-detect selects
the real Gemini provider. Asserts CONTENT, not just status codes.
"""
import io

import pytest


_CSV = "region,sales\nnorth,100\nsouth,200\neast,150\nwest,250\n"


@pytest.mark.usefixtures("_require_llm_key")
def test_golden_path_health_upload_ask(api_client):
    # 1. health -> provider banner says gemini (key is set)
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json()["data"]["provider"] == "gemini"

    # 2. upload a small CSV
    files = {"file": ("sales.csv", io.BytesIO(_CSV.encode()), "text/csv")}
    up = api_client.post("/upload", files=files)
    assert up.status_code == 200, up.text
    dataset_id = up.json()["data"]["dataset_id"]
    assert up.json()["data"]["row_count"] == 4

    # 3. it appears in the datasets list
    listing = api_client.get("/datasets")
    assert listing.status_code == 200
    assert any(d["id"] == dataset_id for d in listing.json()["data"])

    # 4. ask a real question and get a real answer with content
    ask = api_client.post(
        "/ask",
        json={"dataset_id": dataset_id, "question": "What is the total sales across all regions?"},
    )
    assert ask.status_code == 200, ask.text
    answer_data = ask.json()["data"]
    answer = answer_data["answer_markdown"]
    assert answer and "[stub]" not in answer, f"expected a real answer, got: {answer!r}"
    assert any(ch.isdigit() for ch in answer), f"expected a number in the answer: {answer!r}"
    assert answer_data["status"] == "completed"
    run_id = answer_data["run_id"]

    # 5. runs/current reflects the completed run
    current = api_client.get("/runs/current")
    assert current.status_code == 200
    cur = current.json()["data"]
    assert cur["run_id"] == run_id
    assert cur["status"] == "completed"
