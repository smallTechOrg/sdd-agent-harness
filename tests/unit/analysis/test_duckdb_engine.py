"""Unit tests for the DuckDB engine + ingest — no LLM key required."""
import duckdb

from analysis.duckdb_engine import run_query
from analysis.ingest import (
    ingest_csv,
    IngestError,
    FileTooLargeError,
    MAX_UPLOAD_BYTES,
)

import pytest


_CSV = b"order_id,product,revenue\n1,Widget,250.0\n2,Gadget,200.0\n3,Widget,500.0\n"


def test_ingest_extracts_schema_and_row_count(tmp_path):
    res = ingest_csv("t.csv", _CSV, data_dir=tmp_path)
    assert res["row_count"] == 3
    assert res["table_name"] == "data"
    names = {c["name"] for c in res["schema"]}
    assert names == {"order_id", "product", "revenue"}
    # DuckDB types, not Python types.
    types = {c["name"]: c["type"] for c in res["schema"]}
    assert "VARCHAR" in types["product"]
    assert types["revenue"] in ("DOUBLE", "FLOAT", "DECIMAL")


def test_ingest_rejects_empty(tmp_path):
    with pytest.raises(IngestError):
        ingest_csv("e.csv", b"   ", data_dir=tmp_path)


def test_ingest_rejects_too_large(tmp_path):
    big = b"a,b\n" + b"1,2\n" * 10
    # Patch the limit indirectly by feeding content over the cap.
    huge = b"x" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(FileTooLargeError):
        ingest_csv("big.csv", huge, data_dir=tmp_path)


def test_engine_runs_aggregate_query(tmp_path):
    res = ingest_csv("t.csv", _CSV, data_dir=tmp_path)
    rows, error = run_query(
        res["duckdb_path"], "SELECT sum(revenue) AS total FROM data;"
    )
    assert error is None
    assert rows == [{"total": 950.0}]


def test_engine_returns_error_string_on_bad_sql(tmp_path):
    res = ingest_csv("t.csv", _CSV, data_dir=tmp_path)
    rows, error = run_query(
        res["duckdb_path"], "SELECT sum(nonexistent_col) FROM data;"
    )
    assert rows == []
    assert error is not None
    assert isinstance(error, str)
    assert "nonexistent_col" in error.lower() or "binder" in error.lower()


def test_engine_does_not_raise_on_bad_sql(tmp_path):
    res = ingest_csv("t.csv", _CSV, data_dir=tmp_path)
    # Must return, not raise.
    rows, error = run_query(res["duckdb_path"], "THIS IS NOT SQL")
    assert error is not None


def test_engine_caps_result_rows(tmp_path):
    rows_csv = b"n\n" + b"".join(f"{i}\n".encode() for i in range(50))
    res = ingest_csv("big.csv", rows_csv, data_dir=tmp_path)
    rows, error = run_query(
        res["duckdb_path"], "SELECT n FROM data;", max_rows=10
    )
    assert error is None
    assert len(rows) == 10
