"""Prove the aggregation runs over the FULL dataset, not a sample.

The fixture is arranged so the top region by the first 10 rows differs from the
top region over all 32 rows. If we ever silently sampled, this test would fail.
"""

import csv
import os
from collections import defaultdict

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sales.csv")


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


def _sum_by_region(rows):
    totals = defaultdict(int)
    for r in rows:
        totals[r["region"]] += int(r["revenue"])
    return dict(totals)


def _read_fixture_rows():
    with open(FIXTURE, newline="") as f:
        return list(csv.DictReader(f))


def test_full_data_top_region_differs_from_sample():
    """Independently confirm the fixture distinguishes sample from full."""
    rows = _read_fixture_rows()

    sample = _sum_by_region(rows[:10])
    full = _sum_by_region(rows)

    sample_top = max(sample, key=sample.get)
    full_top = max(full, key=full.get)

    assert sample_top == "East"
    assert full_top == "West"
    assert sample_top != full_top  # the discriminating property


def test_run_aggregation_matches_full_not_sample(store):
    from tools.compute import run_aggregation

    rows = _read_fixture_rows()
    expected_full = _sum_by_region(rows)
    expected_sample = _sum_by_region(rows[:10])

    store.load_csv(FIXTURE, "sales_full")
    result = run_aggregation(
        {"group_by": "region", "metric_column": "revenue", "aggregation": "sum"},
        "sales_full",
    )
    computed = {r["region"]: r["revenue"] for r in result["rows"]}

    # The compute equals the full-data answer ...
    assert computed == expected_full
    # ... and is NOT the sample answer (proves we used all rows).
    assert computed != expected_sample
    assert max(computed, key=computed.get) == "West"
