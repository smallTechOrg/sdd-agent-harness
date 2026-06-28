"""API contract tests — no LLM key required, the graph is not invoked.

The runs capability was replaced by the Pandora dataset/question routes, so the
old run-router tests are gone. These cover routing/validation/404s only.
"""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_get_dataset_not_found(api_client):
    r = api_client.get("/datasets/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_get_question_not_found(api_client):
    r = api_client.get("/questions/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_upload_rejects_bad_extension(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PARSE_ERROR"


def test_upload_missing_file(api_client):
    r = api_client.post("/datasets")
    assert r.status_code == 422  # FastAPI validation: required multipart field


def test_ask_unknown_dataset_404(api_client):
    r = api_client.post("/datasets/nope/ask", json={"question": "hi"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_ask_empty_question_rejected(api_client):
    r = api_client.post("/datasets/whatever/ask", json={"question": ""})
    assert r.status_code == 422  # min_length=1 on the request model


def test_cost_today_shape(api_client):
    r = api_client.get("/cost/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data) == {"date", "total_usd", "question_count"}
    assert data["total_usd"] == 0.0
    assert data["question_count"] == 0
