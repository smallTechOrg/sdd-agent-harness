"""End-to-end tests — require real AGENT_GEMINI_API_KEY."""
import io
import pytest


@pytest.fixture
def sales_csv_bytes():
    content = (
        "product_name,quantity,revenue\n"
        "Apple,10,99.99\n"
        "Banana,5,49.50\n"
        "Cherry,20,200.00\n"
        "Date,3,30.00\n"
        "Elderberry,8,80.00\n"
    )
    return content.encode("utf-8")


@pytest.fixture
def empty_result_csv_bytes():
    """CSV where a query returns zero rows (ask for revenue > 9999)."""
    content = (
        "product_name,quantity,revenue\n"
        "Apple,10,99.99\n"
        "Banana,5,49.50\n"
    )
    return content.encode("utf-8")


@pytest.mark.usefixtures("_require_gemini_key")
class TestGoldenPath:
    def test_upload_then_query_full_pipeline(self, api_client, sales_csv_bytes):
        # Step 1: Upload CSV
        r_upload = api_client.post(
            "/upload",
            files={"file": ("sales.csv", io.BytesIO(sales_csv_bytes), "text/csv")},
        )
        assert r_upload.status_code == 200
        session_id = r_upload.json()["data"]["session_id"]

        # Step 2: Ask a numeric aggregation question
        r_query = api_client.post(
            "/query",
            json={
                "session_id": session_id,
                "question": "What is the total revenue by product?",
            },
        )
        assert r_query.status_code == 200
        data = r_query.json()["data"]

        # All three answer fields must be populated
        assert data["status"] == "completed", f"Expected completed, got: {data}"
        assert data["sql"] and len(data["sql"]) > 0, "sql should be non-empty"
        assert data["chart_spec"] is not None, "chart_spec should be set"
        assert "type" in data["chart_spec"], "chart_spec must have type"
        assert data["insight"] and len(data["insight"]) > 20, "insight should be substantive"
        assert data["error"] is None

    def test_sql_starts_with_select(self, api_client, sales_csv_bytes):
        r_upload = api_client.post(
            "/upload",
            files={"file": ("sales.csv", io.BytesIO(sales_csv_bytes), "text/csv")},
        )
        session_id = r_upload.json()["data"]["session_id"]

        r_query = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "What is the total quantity sold?"},
        )
        data = r_query.json()["data"]
        assert data["sql"].upper().lstrip().startswith("SELECT")

    def test_query_run_id_is_uuid_like(self, api_client, sales_csv_bytes):
        r_upload = api_client.post(
            "/upload",
            files={"file": ("sales.csv", io.BytesIO(sales_csv_bytes), "text/csv")},
        )
        session_id = r_upload.json()["data"]["session_id"]

        r_query = api_client.post(
            "/query",
            json={"session_id": session_id, "question": "How many products are there?"},
        )
        data = r_query.json()["data"]
        run_id = data["query_run_id"]
        assert len(run_id) == 36  # UUID length with hyphens


@pytest.mark.usefixtures("_require_gemini_key")
class TestEdgeCases:
    def test_zero_row_result_gives_empty_chart(self, api_client, empty_result_csv_bytes):
        """A question that returns no rows yields chart type 'empty' and status 'completed'."""
        r_upload = api_client.post(
            "/upload",
            files={"file": ("small.csv", io.BytesIO(empty_result_csv_bytes), "text/csv")},
        )
        assert r_upload.status_code == 200
        session_id = r_upload.json()["data"]["session_id"]

        # Ask for items with revenue > 9999 (no such rows in our test data)
        r_query = api_client.post(
            "/query",
            json={
                "session_id": session_id,
                "question": "Which products have revenue greater than 9999?",
            },
        )
        assert r_query.status_code == 200
        data = r_query.json()["data"]
        assert data["status"] == "completed"
        # Chart spec should indicate empty result
        if data.get("chart_spec"):
            assert data["chart_spec"]["type"] == "empty"

    def test_multiple_queries_same_session(self, api_client, sales_csv_bytes):
        """Same session can handle multiple independent queries."""
        r_upload = api_client.post(
            "/upload",
            files={"file": ("sales.csv", io.BytesIO(sales_csv_bytes), "text/csv")},
        )
        session_id = r_upload.json()["data"]["session_id"]

        questions = [
            "What is the total revenue?",
            "Which product has the highest quantity?",
        ]
        run_ids = []
        for q in questions:
            r = api_client.post(
                "/query",
                json={"session_id": session_id, "question": q},
            )
            assert r.status_code == 200
            data = r.json()["data"]
            assert data["status"] == "completed"
            run_ids.append(data["query_run_id"])

        # Each query should get a unique run_id
        assert len(set(run_ids)) == len(questions)
