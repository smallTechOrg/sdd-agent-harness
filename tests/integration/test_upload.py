"""Integration tests for POST /upload — no LLM key required."""
import io
import json
import pytest


def _make_csv(headers: list[str], rows: list[list]) -> io.BytesIO:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    content = "\n".join(lines) + "\n"
    return io.BytesIO(content.encode("utf-8"))


class TestUploadSuccess:
    def test_returns_200(self, api_client):
        csv_buf = _make_csv(["name", "age"], [["Alice", "30"], ["Bob", "25"]])
        r = api_client.post(
            "/upload",
            files={"file": ("people.csv", csv_buf, "text/csv")},
        )
        assert r.status_code == 200

    def test_response_has_session_id(self, api_client):
        csv_buf = _make_csv(["name", "age"], [["Alice", "30"]])
        r = api_client.post(
            "/upload",
            files={"file": ("people.csv", csv_buf, "text/csv")},
        )
        data = r.json()["data"]
        assert "session_id" in data
        assert len(data["session_id"]) > 10

    def test_response_has_correct_row_count(self, api_client):
        csv_buf = _make_csv(["a", "b", "c"], [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]])
        r = api_client.post(
            "/upload",
            files={"file": ("data.csv", csv_buf, "text/csv")},
        )
        assert r.json()["data"]["row_count"] == 3

    def test_response_schema_matches_headers(self, api_client):
        csv_buf = _make_csv(["product", "quantity", "price"], [["Apple", "10", "1.99"]])
        r = api_client.post(
            "/upload",
            files={"file": ("sales.csv", csv_buf, "text/csv")},
        )
        data = r.json()["data"]
        schema = data["schema"]
        col_names = [col["column"] for col in schema]
        assert "product" in col_names
        assert "quantity" in col_names
        assert "price" in col_names

    def test_integer_columns_inferred(self, api_client):
        csv_buf = _make_csv(["name", "count"], [["Alice", "5"]])
        r = api_client.post(
            "/upload",
            files={"file": ("counts.csv", csv_buf, "text/csv")},
        )
        schema = r.json()["data"]["schema"]
        count_col = next(c for c in schema if c["column"] == "count")
        assert count_col["type"] == "INTEGER"

    def test_float_columns_inferred(self, api_client):
        csv_buf = _make_csv(["item", "price"], [["Widget", "9.99"]])
        r = api_client.post(
            "/upload",
            files={"file": ("prices.csv", csv_buf, "text/csv")},
        )
        schema = r.json()["data"]["schema"]
        price_col = next(c for c in schema if c["column"] == "price")
        assert price_col["type"] == "REAL"

    def test_table_name_in_response(self, api_client):
        csv_buf = _make_csv(["x"], [["1"]])
        r = api_client.post(
            "/upload",
            files={"file": ("myfile.csv", csv_buf, "text/csv")},
        )
        data = r.json()["data"]
        assert "table_name" in data
        assert "myfile" in data["table_name"]

    def test_session_persisted_in_db(self, api_client, _isolated_db):
        csv_buf = _make_csv(["col1"], [["val1"]])
        r = api_client.post(
            "/upload",
            files={"file": ("test_persist.csv", csv_buf, "text/csv")},
        )
        session_id = r.json()["data"]["session_id"]

        from sqlalchemy.orm import Session
        from db.models import UploadSession
        with Session(_isolated_db) as s:
            upload = s.get(UploadSession, session_id)
        assert upload is not None
        assert upload.row_count == 1


class TestUploadErrors:
    def test_wrong_extension_returns_422(self, api_client):
        r = api_client.post(
            "/upload",
            files={"file": ("data.txt", io.BytesIO(b"a,b\n1,2"), "text/plain")},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "UNSUPPORTED_FORMAT"

    def test_json_extension_returns_422(self, api_client):
        r = api_client.post(
            "/upload",
            files={"file": ("data.json", io.BytesIO(b'{"a":1}'), "application/json")},
        )
        assert r.status_code == 422

    def test_empty_csv_no_rows_returns_422(self, api_client):
        # Headers only, no data rows
        csv_buf = io.BytesIO(b"name,age\n")
        r = api_client.post(
            "/upload",
            files={"file": ("empty.csv", csv_buf, "text/csv")},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "INVALID_CSV"
