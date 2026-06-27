"""Phase-1 gate: NL question -> SQL + table + chart, end-to-end.

Runs against REAL Gemini (AGENT_GEMINI_API_KEY from .env) and a real in-process
DuckDB seeded with the `sales` table (via the integration conftest fixture).
Drives the FULL path through the FastAPI TestClient.
"""
import json

import pytest

_VALID_CHART_TYPES = {"bar", "line", "pie", "scatter", "table"}


@pytest.mark.usefixtures("_require_llm_key")
def test_nl_question_returns_sql_table_and_chart(api_client):
    """The core happy path: a real question yields SQL + non-empty results + chart."""
    r = api_client.post("/runs", json={"input_text": "What were total sales by region?"})
    assert r.status_code == 200, r.text

    body = r.json()
    data = body["data"]
    assert data["status"] == "completed", data
    assert not body.get("error")

    payload = json.loads(data["output_text"])

    # SQL: a single SELECT touching the sales table.
    sql = payload["sql"]
    assert sql, "expected a generated SQL statement"
    lowered = sql.lower().lstrip()
    assert lowered.startswith("select") or lowered.startswith("with")
    assert "sales" in lowered
    assert ";" not in sql.rstrip().rstrip(";"), "expected a single statement"

    # Table: non-empty columns + rows.
    assert payload["columns"], "expected non-empty columns"
    assert payload["rows"], "expected non-empty rows"

    # Chart: a valid chart_spec with a valid enum chart_type.
    chart = payload["chart_spec"]
    assert chart is not None
    assert chart["chart_type"] in _VALID_CHART_TYPES

    # Privacy/error contract: success payload carries error=null.
    assert payload["error"] is None


def test_guard_rejects_non_select_with_graceful_failure_shape(api_client):
    """Hard case: a non-SELECT from the planner must produce the graceful failure JSON.

    We assert the contract directly by driving execute_sql's guard with a
    non-read-only statement, confirming the run fails gracefully (no crash, no
    execution) and renders the documented failure payload shape.
    """
    from graph.nodes import execute_sql, handle_error

    state = {"run_id": "test-run", "sql": "DROP TABLE sales"}
    after_exec = execute_sql(state)
    assert after_exec.get("error"), "guard must set an error for a non-SELECT"

    final = handle_error(after_exec)
    assert final["status"] == "failed"

    payload = json.loads(final["output_text"])
    # Documented failure shape: empty columns/rows, null chart_spec, error set.
    assert payload["columns"] == []
    assert payload["rows"] == []
    assert payload["chart_spec"] is None
    assert payload["error"]
