"""Integration tests for the graph runner — kept for backwards compatibility.

The primary integration tests are in test_upload.py and test_query_pipeline.py.
"""
import io
import pytest


@pytest.mark.usefixtures("_require_gemini_key")
def test_graph_runner_end_to_end(api_client):
    """Full HTTP round-trip: upload + query."""
    csv_content = "name,score\nAlice,95\nBob,87\nCarol,92\n"
    r_upload = api_client.post(
        "/upload",
        files={"file": ("grades.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r_upload.status_code == 200
    session_id = r_upload.json()["data"]["session_id"]

    r_query = api_client.post(
        "/query",
        json={"session_id": session_id, "question": "Who has the highest score?"},
    )
    assert r_query.status_code == 200
    body = r_query.json()
    assert body["data"]["status"] == "completed"
    assert body["data"]["sql"]
    assert not body["data"].get("error")
