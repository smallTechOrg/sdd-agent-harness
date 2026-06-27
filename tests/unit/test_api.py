"""API contract tests — no LLM key required, graph is not invoked."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_list_datasets_empty(api_client):
    """GET /datasets returns empty list when no datasets exist."""
    r = api_client.get("/datasets")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_upload_invalid_file_type(api_client):
    """Upload with non-CSV/Excel extension returns 422."""
    r = api_client.post("/datasets", files={"file": ("report.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_upload_valid_csv(api_client):
    """Upload a small valid CSV returns 200 with dataset_id and row_count."""
    csv_content = b"name,value\nfoo,1\nbar,2\nbaz,3\n"
    r = api_client.post("/datasets", files={"file": ("test.csv", csv_content, "text/csv")})
    assert r.status_code == 200, f"Upload failed: {r.text}"
    data = r.json()["data"]
    assert data["dataset_id"]
    assert data["filename"] == "test.csv"
    assert "name" in data["columns"]
    assert "value" in data["columns"]
    assert data["row_count"] == 3


def test_upload_csv_then_list(api_client):
    """After uploading a CSV, GET /datasets shows it."""
    csv_content = b"x,y\n1,2\n3,4\n"
    api_client.post("/datasets", files={"file": ("sample.csv", csv_content, "text/csv")})
    r = api_client.get("/datasets")
    assert r.status_code == 200
    items = r.json()["data"]
    assert len(items) == 1
    assert items[0]["filename"] == "sample.csv"


def test_analyze_missing_dataset(api_client):
    """POST /analyze with unknown dataset_id returns 500."""
    r = api_client.post("/analyze", json={
        "dataset_id": "00000000-0000-0000-0000-000000000000",
        "question": "What is the total?",
    })
    assert r.status_code == 500


def test_analyze_missing_body(api_client):
    """POST /analyze with empty body returns 422."""
    r = api_client.post("/analyze", json={})
    assert r.status_code == 422
