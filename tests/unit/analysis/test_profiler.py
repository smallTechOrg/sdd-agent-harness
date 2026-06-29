"""Unit tests for profile_dataset — stats must match a direct DuckDB query."""
from pathlib import Path

import duckdb
import pytest

from analysis.ingest import ingest_csv
from analysis.profiler import profile_dataset

_SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "sales.csv"


@pytest.fixture
def ingested(tmp_path):
    content = _SAMPLE.read_bytes()
    return ingest_csv("sales.csv", content, data_dir=tmp_path)


def test_profile_has_one_entry_per_column(ingested):
    profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    assert len(profile) == len(ingested["schema"])
    assert [p["column"] for p in profile] == [c["name"] for c in ingested["schema"]]


def test_profile_matches_direct_duckdb_query(ingested):
    profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    by_col = {p["column"]: p for p in profile}

    con = duckdb.connect(ingested["duckdb_path"], read_only=True)
    try:
        for name in ("revenue", "region", "order_id"):
            null_count, distinct = con.execute(
                f'SELECT count(*)-count("{name}"), count(DISTINCT "{name}") FROM data'
            ).fetchone()
            entry = by_col[name]
            assert entry["null_count"] == null_count, name
            assert entry["distinct_count"] == distinct, name
    finally:
        con.close()


def test_profile_numeric_minmax_correct(ingested):
    profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    revenue = next(p for p in profile if p["column"] == "revenue")
    assert float(revenue["min"]) == 120.0
    assert float(revenue["max"]) == 660.0
    assert revenue["null_count"] == 0
    assert revenue["distinct_count"] == 12


def test_profile_non_numeric_has_no_minmax(ingested):
    profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    region = next(p for p in profile if p["column"] == "region")
    assert region["min"] is None
    assert region["max"] is None
    assert region["distinct_count"] == 4


def test_profile_quality_flags_constant_and_high_null(tmp_path):
    # A 4-row CSV: const column (all same), allnull column (all empty).
    csv = b"id,const,mostly_null\n1,X,\n2,X,\n3,X,5\n4,X,\n"
    ingested = ingest_csv("q.csv", csv, data_dir=tmp_path)
    profile = profile_dataset(ingested["duckdb_path"], ingested["schema"])
    by_col = {p["column"]: p for p in profile}
    assert "constant" in by_col["const"]["flags"]
    # mostly_null: 3 of 4 null -> > 0.5 -> high_null.
    assert "high_null" in by_col["mostly_null"]["flags"]


def test_profile_edge_empty_schema(ingested):
    # Edge case: empty schema yields an empty profile, not an error.
    assert profile_dataset(ingested["duckdb_path"], []) == []
