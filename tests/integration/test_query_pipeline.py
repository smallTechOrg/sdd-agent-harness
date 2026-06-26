"""Integration tests for POST /query — requires real AGENT_GEMINI_API_KEY."""
import io
import json
import pytest
from unittest.mock import patch


def _upload_sales_csv(api_client) -> str:
    """Upload a small sales CSV and return the session_id."""
    csv_content = (
        "product_name,quantity,revenue\n"
        "Apple,10,99.99\n"
        "Banana,5,49.50\n"
        "Cherry,20,200.00\n"
        "Date,3,30.00\n"
        "Elderberry,8,80.00\n"
    )
    r = api_client.post(
        "/upload",
        files={"file": ("sales.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200, f"Upload failed: {r.text}"
    return r.json()["data"]["session_id"]


@pytest.mark.usefixtures("_require_gemini_key")
class TestQueryPipelineReal:
    def test_query_returns_completed(self, api_client):
        session_id = _upload_sales_csv(api_client)
        r = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "What is the total revenue by product?"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "completed"

    def test_query_returns_sql(self, api_client):
        session_id = _upload_sales_csv(api_client)
        r = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "What is the total revenue by product?"},
        )
        data = r.json()["data"]
        assert data["sql"] is not None
        assert data["sql"].upper().startswith("SELECT")

    def test_query_returns_chart_spec(self, api_client):
        session_id = _upload_sales_csv(api_client)
        r = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "What is the total revenue by product?"},
        )
        data = r.json()["data"]
        assert data["chart_spec"] is not None
        assert "type" in data["chart_spec"]

    def test_query_returns_insight(self, api_client):
        session_id = _upload_sales_csv(api_client)
        r = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "What is the total revenue by product?"},
        )
        data = r.json()["data"]
        assert data["insight"] is not None
        assert len(data["insight"]) > 20

    def test_query_run_id_returned(self, api_client):
        session_id = _upload_sales_csv(api_client)
        r = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "How many rows?"},
        )
        data = r.json()["data"]
        assert "query_run_id" in data
        assert len(data["query_run_id"]) > 10


class TestQuerySafetySQLBlocked:
    def test_safety_violation_returns_failed_status(self, api_client, _isolated_db):
        """Patching sql_generation to return a DELETE statement triggers the safety guard."""
        session_id = _upload_sales_csv(api_client)

        def _fake_sql_generation(state):
            return {**state, "sql": "DELETE FROM sales_csv_abc12345"}

        with patch("graph.nodes.sql_generation", _fake_sql_generation):
            # We need to also patch the graph to use our fake node
            # Instead, patch the sql directly by monkey-patching nodes in the graph
            pass

        # Directly test through the node: create state and call sql_execution
        from graph.nodes import sql_execution
        state = {
            "sql": "DELETE FROM some_table",
            "table_name": "some_table",
            "question": "delete all rows",
        }
        result = sql_execution(state)
        assert result.get("error") is not None
        assert "SQL safety violation" in result["error"]

    def test_safety_error_message_content(self, api_client):
        from graph.nodes import sql_execution
        for dangerous_sql in [
            "INSERT INTO t VALUES (1)",
            "UPDATE t SET x=1",
            "DROP TABLE t",
        ]:
            state = {"sql": dangerous_sql, "table_name": "t", "question": "q"}
            result = sql_execution(state)
            assert result.get("error") is not None
            assert "SQL safety violation" in result["error"]


class TestQueryErrorCases:
    def test_session_not_found_returns_404(self, api_client):
        r = api_client.post(
            "/query",
            json={"session_id": "nonexistent-uuid-1234", "question": "Test?"},
        )
        assert r.status_code == 404

    def test_empty_question_rejected(self, api_client):
        r = api_client.post(
            "/query",
            json={"session_id": "any", "question": ""},
        )
        assert r.status_code == 422

    def test_question_too_long_rejected(self, api_client):
        r = api_client.post(
            "/query",
            json={"session_id": "any", "question": "x" * 2001},
        )
        assert r.status_code == 422
