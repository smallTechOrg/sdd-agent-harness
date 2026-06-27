"""The privacy boundary — the heart of DataChat.

assert_no_raw_rows is the single chokepoint between local compute and the LLM.
These tests prove: valid schema/aggregate payloads pass; raw-row payloads are
rejected; and a unique sentinel cell value in the data never appears in any
LLM-bound payload.

Fully local — no LLM, no network.
"""

import os

import pytest

from tools.compute import (
    MAX_AGGREGATE_ROWS,
    PrivacyBoundaryError,
    assert_no_raw_rows,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sales.csv")
SENTINEL = "SENTINEL_UNIQUE_CELL_XYZ123"


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_path = str(tmp_path / "working.duckdb")
    monkeypatch.setenv("DATACHAT_DUCKDB_PATH", db_path)
    import tools.duckdb_store as ds

    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None
    yield ds
    if ds._conn is not None:
        ds._conn.close()
    ds._conn = None
    ds._conn_path = None


# --- (a) valid payloads pass -------------------------------------------------

def test_schema_summary_passes():
    payload = {
        "row_count": 100,
        "columns": [
            {"name": "region", "type": "text", "distinct": 5, "nulls": 0},
            {"name": "revenue", "type": "number", "min": 0, "max": 9, "nulls": 0},
        ],
    }
    assert assert_no_raw_rows(payload) is payload


def test_bounded_aggregate_result_passes():
    payload = {
        "group_by": "region",
        "metric": "revenue",
        "aggregation": "sum",
        "rows": [{"region": "West", "revenue": 410000}],
    }
    assert assert_no_raw_rows(payload) is payload


# --- (b) raw-row / oversized / sentinel payloads are rejected ----------------

def test_raw_rows_marker_rejected():
    payload = {
        "group_by": "region",
        "aggregation": "sum",
        "rows": [{"region": "West", "revenue": 1}],
        "__raw_rows__": True,
    }
    with pytest.raises(PrivacyBoundaryError):
        assert_no_raw_rows(payload)


def test_oversized_row_list_rejected():
    payload = {
        "group_by": "id",
        "metric": "revenue",
        "aggregation": "sum",
        "rows": [{"id": i, "revenue": i} for i in range(MAX_AGGREGATE_ROWS + 1)],
    }
    with pytest.raises(PrivacyBoundaryError):
        assert_no_raw_rows(payload)


def test_unrecognised_shape_rejected():
    with pytest.raises(PrivacyBoundaryError):
        assert_no_raw_rows({"some": "thing"})


def test_non_dict_rejected():
    with pytest.raises(PrivacyBoundaryError):
        assert_no_raw_rows([{"region": "West"}])  # type: ignore[arg-type]


def test_schema_summary_with_rows_rejected():
    payload = {
        "row_count": 3,
        "columns": [{"name": "region", "type": "text", "distinct": 1, "nulls": 0}],
        "rows": [{"region": "West"}],
    }
    with pytest.raises(PrivacyBoundaryError):
        assert_no_raw_rows(payload)


# --- (c) sentinel: real payloads never carry a raw cell value ----------------

def test_sentinel_absent_from_real_payloads(store):
    from tools.profile import build_schema_summary
    from tools.compute import run_aggregation

    store.load_csv(FIXTURE, "sentinel_ds")

    schema = build_schema_summary("sentinel_ds")
    aggregate = run_aggregation(
        {"group_by": "region", "metric_column": "revenue", "aggregation": "sum"},
        "sentinel_ds",
    )

    # Both must pass the guard ...
    assert assert_no_raw_rows(schema) is schema
    assert assert_no_raw_rows(aggregate) is aggregate

    # ... and neither must contain the unique sentinel cell value.
    assert SENTINEL not in repr(schema)
    assert SENTINEL not in repr(aggregate)
    # Nor any other raw note cell.
    assert "alpha" not in repr(schema)
    assert "alpha" not in repr(aggregate)
