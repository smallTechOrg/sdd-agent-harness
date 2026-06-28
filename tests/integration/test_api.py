"""Integration tests for the Pandora API routes.

The upload + profile + fetch + cost paths run without an LLM key (suggestions
degrade gracefully). The ``/ask`` SSE path invokes the real graph against real
Gemini and is skipped when no key is present.
"""
import json

import pytest

_SMALL_CSV = (
    b"region,product,revenue,quantity\n"
    b"North,Widget,100.0,2\n"
    b"South,Gadget,250.0,5\n"
    b"North,Gadget,150.0,3\n"
    b"East,Widget,300.0,6\n"
    b"South,Widget,120.0,2\n"
)


def _upload_small(api_client) -> dict:
    r = api_client.post(
        "/datasets",
        files={"file": ("mini.csv", _SMALL_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_upload_dataset_profiles_and_persists(api_client, _isolated_db):
    data = _upload_small(api_client)

    assert data["filename"] == "mini.csv"
    assert data["row_count"] == 5
    assert data["column_count"] == 4
    assert data["status"] == "ready"

    profile = data["profile"]
    assert profile["row_count"] == 5
    assert profile["column_count"] == 4
    col_names = {c["name"] for c in profile["columns"]}
    assert {"region", "product", "revenue", "quantity"} <= col_names

    # Suggestions are present (LLM or graceful fallback) — never empty here.
    assert isinstance(data["suggested_questions"], list)
    assert len(data["suggested_questions"]) >= 1

    # A datasets row exists.
    from sqlalchemy.orm import Session
    from db.models import Dataset

    with Session(_isolated_db) as s:
        row = s.get(Dataset, data["dataset_id"])
        assert row is not None
        assert row.status == "ready"
        assert json.loads(row.profile_json)["row_count"] == 5


def test_get_dataset_roundtrip(api_client):
    data = _upload_small(api_client)
    r = api_client.get(f"/datasets/{data['dataset_id']}")
    assert r.status_code == 200
    got = r.json()["data"]
    assert got["dataset_id"] == data["dataset_id"]
    assert got["profile"]["row_count"] == 5
    assert got["status"] == "ready"


def test_get_unknown_dataset_404(api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_upload_parse_error_persists_nothing(api_client, _isolated_db):
    # A .csv that pandas cannot parse into columns.
    r = api_client.post(
        "/datasets",
        files={"file": ("bad.csv", b"", "text/csv")},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PARSE_ERROR"

    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from db.models import Dataset

    with Session(_isolated_db) as s:
        count = s.execute(select(func.count(Dataset.id))).scalar_one()
        assert count == 0


def test_cost_today_empty(api_client):
    r = api_client.get("/cost/today")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["question_count"] == 0
    assert data["total_usd"] == 0.0


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse an SSE body into a list of (event_name, data_dict)."""
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
        elif line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"_raw": raw}
                events.append((event_name, payload))
            event_name = "message"
            data_lines = []
    if data_lines:  # trailing event without blank line
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {"_raw": "\n".join(data_lines)}
        events.append((event_name, payload))
    return events


def test_ask_streams_steps_and_answer(api_client, _require_llm_key):
    """Real Gemini: upload, ask, consume the SSE stream, assert step + answer."""
    data = _upload_small(api_client)
    dataset_id = data["dataset_id"]

    with api_client.stream(
        "POST",
        f"/datasets/{dataset_id}/ask",
        json={"question": "What is the total revenue by region?"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(resp.iter_text())

    events = _parse_sse(body)
    names = [n for n, _ in events]
    assert "step" in names, f"expected at least one step event, got {names}"

    terminal = [(n, d) for n, d in events if n in ("answer", "error")]
    assert terminal, f"expected a terminal answer/error event, got {names}"
    name, payload = terminal[-1]
    assert name == "answer", f"expected an answer, got {name}: {payload}"

    assert payload["status"] == "completed"
    assert payload.get("answer_text")
    assert payload["question_id"]
    assert "usage" in payload
    assert "daily_total_usd" in payload
    assert payload["daily_total_usd"] >= 0.0

    # The question is persisted and revisitable.
    r = api_client.get(f"/questions/{payload['question_id']}")
    assert r.status_code == 200
    q = r.json()["data"]
    assert q["status"] == "completed"
    assert q["answer_text"]

    # Daily cost reflects the asked question.
    c = api_client.get("/cost/today").json()["data"]
    assert c["question_count"] >= 1
