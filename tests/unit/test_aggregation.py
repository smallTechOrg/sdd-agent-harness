"""Aggregation engine tests — the privacy firewall.

These assert exact arithmetic over known fixtures, the 50-row cap, the
missing-column error path, and (critically) that aggregation runs over the FULL
file rather than a truncated sample.
"""
import pytest

from data.aggregation import MAX_ROWS, run_plan
from tests.fixtures.datasets import write_large_csv, write_small_csv


def _plan(**overrides) -> dict:
    base = {
        "group_by": ["region"],
        "metric": "sales",
        "agg": "sum",
        "filter": None,
        "sort": "desc",
        "limit": 50,
        "intent": "comparison",
    }
    base.update(overrides)
    return base


def test_group_by_sum_exact(tmp_path):
    path = write_small_csv(str(tmp_path))
    out = run_plan(path, _plan(agg="sum"))

    sums = {r["region"]: r["sum_sales"] for r in out["rows"]}
    # West: 100+300=400, East: 200+400=600, North: 500
    assert sums == {"West": 400, "East": 600, "North": 500}
    assert out["intent"] == "comparison"
    assert "region" in out["columns"] and "sum_sales" in out["columns"]


def test_group_by_mean_exact(tmp_path):
    path = write_small_csv(str(tmp_path))
    out = run_plan(path, _plan(agg="mean"))
    means = {r["region"]: r["mean_sales"] for r in out["rows"]}
    assert means["West"] == 200.0  # (100+300)/2
    assert means["East"] == 300.0  # (200+400)/2
    assert means["North"] == 500.0


def test_group_by_count_exact(tmp_path):
    path = write_small_csv(str(tmp_path))
    out = run_plan(path, _plan(agg="count", metric=None))
    counts = {r["region"]: r["count"] for r in out["rows"]}
    assert counts == {"West": 2, "East": 2, "North": 1}


def test_missing_column_raises(tmp_path):
    path = write_small_csv(str(tmp_path))
    with pytest.raises(ValueError):
        run_plan(path, _plan(group_by=["does_not_exist"]))
    with pytest.raises(ValueError):
        run_plan(path, _plan(metric="nope"))


def test_rows_capped_at_50(tmp_path):
    # 60 distinct groups, but the cap is 50 even when plan.limit asks for more.
    path, _ = write_large_csv(str(tmp_path))
    # Make every row its own group so there are 600 groups.
    import pandas as pd

    df = pd.DataFrame({"region": [f"k{i}" for i in range(600)], "amount": range(600)})
    big = str(tmp_path / "many_groups.csv")
    df.to_csv(big, index=False)

    out = run_plan(big, _plan(group_by=["region"], metric="amount", limit=9999))
    assert len(out["rows"]) == MAX_ROWS == 50


def test_full_file_aggregation_not_sampled(tmp_path):
    """Prove aggregation runs over the full file, not head(50).

    With >=500 rows and >=12 groups, the full-file per-group sums must differ
    from the sums computed over only the first 50 rows.
    """
    path, expected = write_large_csv(str(tmp_path))
    assert expected["rows"] >= 500
    assert expected["groups"] >= 12

    out = run_plan(path, _plan(group_by=["region"], metric="amount", sort="asc"))
    got = {r["region"]: r["sum_amount"] for r in out["rows"]}

    # Exact full-file sums.
    assert got == expected["full_sum_by_group"]
    # And the full-file total differs from a head(50) sample total — so the
    # engine cannot have silently truncated the input.
    assert expected["full_total"] != expected["sample_total"]
    assert sum(got.values()) == expected["full_total"]


def test_run_plan_returns_only_aggregates(tmp_path):
    """The result envelope carries only aggregated rows + columns + intent."""
    path = write_small_csv(str(tmp_path))
    out = run_plan(path, _plan())
    assert set(out.keys()) == {"rows", "columns", "intent"}
    # Each returned row's keys are exactly the aggregate columns — no raw fields
    # like the un-aggregated "sales" or "date" leak through.
    for row in out["rows"]:
        assert set(row.keys()) == set(out["columns"])
    assert "date" not in out["columns"]
