"""API contract tests — no LLM key required."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_upload_wrong_extension(api_client):
    import io
    r = api_client.post(
        "/upload",
        files={"file": ("data.txt", io.BytesIO(b"a,b\n1,2"), "text/plain")},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"


def test_query_session_not_found(api_client):
    r = api_client.post("/query", json={"session_id": "nonexistent", "question": "What?"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SESSION_NOT_FOUND"


def test_query_empty_question_rejected(api_client):
    r = api_client.post("/query", json={"session_id": "abc", "question": ""})
    assert r.status_code == 422


def test_query_missing_body(api_client):
    r = api_client.post("/query", json={})
    assert r.status_code == 422
