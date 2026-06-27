"""Local compute slice: CSV ingest, schema profiling, full-data aggregation.

These tests are fully local — no LLM, no network.
"""

import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sales.csv")


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the DuckDB working store at an isolated temp file per test."""
    db_path = str(tmp_path / "working.duckdb")
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", db_path)
    import tools.duckdb_store as ds

    # Reset the module-level connection so it reopens at the temp path.
    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None
    yield ds
    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None


def test_load_csv_returns_row_count(store):
    n = store.load_csv(FIXTURE, "sales1")
    assert n == 32  # 32 data rows in the fixture


def test_table_name_is_deterministic_and_safe(store):
    a = store.table_name("abc-123 def")
    b = store.table_name("abc-123 def")
    assert a == b
    assert a.replace("_", "").replace("ds", "", 1)  # only alnum + underscores
    assert all(ch.isalnum() or ch == "_" for ch in a)


def test_build_schema_summary_shape_and_values(store):
    from tools.profile import build_schema_summary

    store.load_csv(FIXTURE, "sales1")
    summary = build_schema_summary("sales1")

    assert set(summary.keys()) == {"row_count", "columns"}
    assert summary["row_count"] == 32

    cols = {c["name"]: c for c in summary["columns"]}
    assert set(cols) == {"region", "month", "revenue", "note"}

    region = cols["region"]
    assert region["type"] == "text"
    assert region["distinct"] == 4  # East, West, North, South
    assert region["nulls"] == 0
    assert "min" not in region and "max" not in region  # no min/max on text

    revenue = cols["revenue"]
    assert revenue["type"] == "number"
    assert revenue["min"] == 50
    assert revenue["max"] == 800
    assert revenue["nulls"] == 0


def test_schema_summary_has_no_raw_cell_values(store):
    """The schema payload must contain only scalars, never raw cell strings."""
    from tools.profile import build_schema_summary

    store.load_csv(FIXTURE, "sales1")
    summary = build_schema_summary("sales1")

    blob = repr(summary)
    assert "SENTINEL_UNIQUE_CELL_XYZ123" not in blob
    assert "alpha" not in blob  # a note cell value must not appear


def test_run_aggregation_sum_by_region_full_data(store):
    from tools.compute import run_aggregation

    store.load_csv(FIXTURE, "sales1")
    plan = {"group_by": "region", "metric_column": "revenue", "aggregation": "sum"}
    result = run_aggregation(plan, "sales1")

    assert result["group_by"] == "region"
    assert result["metric"] == "revenue"
    assert result["aggregation"] == "sum"

    totals = {r["region"]: r["revenue"] for r in result["rows"]}
    # Hand-computed over the FULL 32-row fixture.
    assert totals == {"West": 8300, "East": 3500, "North": 1550, "South": 1050}
    # Ordered by metric desc.
    assert [r["region"] for r in result["rows"]] == ["West", "East", "North", "South"]


def test_run_aggregation_count_per_group(store):
    from tools.compute import run_aggregation

    store.load_csv(FIXTURE, "sales1")
    plan = {"group_by": "region", "aggregation": "count"}
    result = run_aggregation(plan, "sales1")
    counts = {r["region"]: r["count"] for r in result["rows"]}
    assert counts == {"West": 13, "East": 7, "North": 6, "South": 6}


def test_run_aggregation_rejects_unknown_column(store):
    from tools.compute import run_aggregation

    store.load_csv(FIXTURE, "sales1")
    with pytest.raises(ValueError):
        run_aggregation(
            {"group_by": "nope", "metric_column": "revenue", "aggregation": "sum"},
            "sales1",
        )


def test_load_csv_missing_file_raises(store):
    with pytest.raises(FileNotFoundError):
        store.load_csv("/no/such/file.csv", "x")
