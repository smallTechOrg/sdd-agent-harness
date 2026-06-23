"""API contract tests — no LLM key required, graph is not invoked."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_datasets_list_empty(api_client):
    """GET /datasets returns the envelope with an empty list by default."""
    r = api_client.get("/datasets")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["data"] == []


def test_audit_list_empty(api_client):
    r = api_client.get("/audit")
    assert r.status_code == 200
    body = r.json()
    assert body["error"] is None
    assert body["data"] == []


def test_ask_empty_question_rejected(api_client):
    """Empty question is a 400 before any LLM/graph work."""
    r = api_client.post("/ask", json={"dataset_id": "x", "question": "   "})
    assert r.status_code == 400


def test_ask_missing_body_422(api_client):
    r = api_client.post("/ask", json={})
    assert r.status_code == 422


def test_ask_unknown_dataset_400(api_client):
    """Unknown dataset is rejected with 400 (no LLM call)."""
    r = api_client.post("/ask", json={"dataset_id": "nope", "question": "anything?"})
    assert r.status_code == 400


def test_upload_empty_file_rejected(api_client):
    import io

    r = api_client.post(
        "/datasets",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert r.status_code == 400


def test_audit_export_csv_headers(api_client):
    r = api_client.get("/audit/export", params={"format": "csv"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")
