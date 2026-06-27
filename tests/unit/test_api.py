"""API contract tests — no LLM key required, graph is not invoked."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_analyses_missing_body_rejected(api_client):
    """POST /analyses with no body is a 422 validation error (graph never runs)."""
    r = api_client.post("/analyses", json={})
    assert r.status_code == 422


def test_get_analysis_not_found(api_client):
    r = api_client.get("/analyses/nonexistent-id")
    assert r.status_code == 404
