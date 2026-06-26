"""Offline API suite for the Phase-2 routes.

Stub provider + in-memory SQLite, zero network. Exercises the full upload ->
datasets -> ask -> runs journey through the `api_client` TestClient. The stub
LLM returns node-tagged canned output, so `/ask` returns a `[stub]` answer with
recorded steps — enough to prove the route plumbing end to end without a key.
"""
import io

import pytest


@pytest.fixture(autouse=True)
def _force_stub_provider(monkeypatch):
    """Pin the offline stub provider regardless of any key present in `.env`.

    This suite is the offline guarantee — no network even when a real key is
    configured locally. Set ahead of the settings-singleton reset so both the
    graph and `/health` resolve to `stub`.
    """
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "stub")
    import config.settings as m
    m._settings = None


_CSV = "value,label\n10,a\n20,b\n30,c\n"


def _upload_csv(client, *, name="sample.csv", body=_CSV):
    files = {"file": (name, io.BytesIO(body.encode()), "text/csv")}
    return client.post("/upload", files=files)


# --- upload --------------------------------------------------------------


def test_upload_csv_returns_counts(api_client):
    r = _upload_csv(api_client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["filename"] == "sample.csv"
    assert data["format"] == "csv"
    assert data["row_count"] == 3
    assert data["col_count"] == 2
    assert data["columns"] == ["value", "label"]
    # Phase 2 does NOT trigger async notes.
    assert data["auto_notes_status"] is None


def test_upload_rejects_bad_extension(api_client):
    files = {"file": ("notes.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    r = api_client.post("/upload", files=files)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] in ("bad_extension", "unparseable_file")


def test_upload_rejects_empty_file(api_client):
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    r = api_client.post("/upload", files=files)
    assert r.status_code == 400


def test_duplicate_upload_returns_409(api_client):
    first = _upload_csv(api_client)
    assert first.status_code == 200
    dup = _upload_csv(api_client)
    assert dup.status_code == 409
    detail = dup.json()["detail"]
    assert detail["code"] == "duplicate_dataset"
    assert detail["match_type"] in ("content_and_name", "content", "name")
    assert detail["existing_dataset_id"] == first.json()["data"]["dataset_id"]


def test_duplicate_upload_force_overrides(api_client):
    first = _upload_csv(api_client)
    assert first.status_code == 200
    forced = api_client.post(
        "/upload?force=true",
        files={"file": ("sample.csv", io.BytesIO(_CSV.encode()), "text/csv")},
    )
    assert forced.status_code == 200
    assert forced.json()["data"]["dataset_id"] != first.json()["data"]["dataset_id"]


# --- datasets ------------------------------------------------------------


def test_datasets_list_includes_uploaded(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.get("/datasets")
    assert r.status_code == 200
    rows = r.json()["data"]
    assert any(d["id"] == dataset_id for d in rows)
    row = next(d for d in rows if d["id"] == dataset_id)
    assert row["origin"] == "uploaded"
    assert row["stale"] is False
    assert row["derivation_description"] is None


def test_dataset_detail_has_columns_schema(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.get(f"/datasets/{dataset_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    schema = {c["name"]: c["dtype"] for c in data["columns_schema"]}
    assert schema["value"] == "integer"
    assert schema["label"] == "text"


def test_dataset_detail_404_when_missing(api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404


def test_dataset_preview_returns_rows(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.get(f"/datasets/{dataset_id}/preview?rows=2")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["columns"] == ["value", "label"]
    assert len(data["rows"]) == 2
    assert data["rows"][0]["value"] == 10


def test_dataset_preview_formats_nan_as_null(api_client):
    body = "value,label\n10,a\n,b\n"
    up = _upload_csv(api_client, name="withnan.csv", body=body)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.get(f"/datasets/{dataset_id}/preview")
    assert r.status_code == 200
    rows = r.json()["data"]["rows"]
    # second row's `value` is NaN -> null
    assert rows[1]["value"] is None


def test_delete_dataset_removes_it(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.delete(f"/datasets/{dataset_id}")
    assert r.status_code == 200
    assert api_client.get(f"/datasets/{dataset_id}").status_code == 404


def test_delete_dataset_404_when_missing(api_client):
    r = api_client.delete("/datasets/does-not-exist")
    assert r.status_code == 404


def test_delete_all_datasets(api_client):
    _upload_csv(api_client)
    _upload_csv(api_client, name="other.csv", body="x,y\n1,2\n")
    r = api_client.delete("/datasets")
    assert r.status_code == 200
    assert api_client.get("/datasets").json()["data"] == []


# --- ask + runs ----------------------------------------------------------


def test_ask_single_dataset_returns_answer(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    r = api_client.post("/ask", json={"dataset_id": dataset_id, "question": "describe it"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["type"] == "answer"
    assert data["run_id"]
    assert data["dataset_ids"] == [dataset_id]
    assert data["answer_markdown"]  # stub answer is non-empty
    assert data["answer_html"]  # rendered from markdown
    assert isinstance(data["steps"], list)
    assert len(data["steps"]) >= 1
    assert data["status"] == "completed"
    assert data["suggested_questions"] == []
    assert data["prompt_breakdown"] == {}


def test_ask_404_when_dataset_missing(api_client):
    r = api_client.post("/ask", json={"dataset_id": "ghost", "question": "hi"})
    assert r.status_code == 404


def test_runs_current_reflects_last_run(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    ask = api_client.post("/ask", json={"dataset_id": dataset_id, "question": "describe it"})
    run_id = ask.json()["data"]["run_id"]
    r = api_client.get("/runs/current")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["run_id"] == run_id
    assert data["status"] == "completed"


def test_get_run_by_id_returns_query_run(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    ask = api_client.post("/ask", json={"dataset_id": dataset_id, "question": "describe it"})
    run_id = ask.json()["data"]["run_id"]
    r = api_client.get(f"/runs/{run_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["run_id"] == run_id
    assert data["status"] == "completed"
    assert "iteration_count" in data


# --- stats ---------------------------------------------------------------


def test_stats_daily_always_200(api_client):
    r = api_client.get("/stats/daily")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "date" in data
    assert "model" in data
    assert data["context_limit"] >= 1
    assert data["query_count"] == 0


def test_stats_daily_counts_completed_runs(api_client):
    up = _upload_csv(api_client)
    dataset_id = up.json()["data"]["dataset_id"]
    api_client.post("/ask", json={"dataset_id": dataset_id, "question": "describe it"})
    r = api_client.get("/stats/daily")
    data = r.json()["data"]
    assert data["query_count"] == 1
