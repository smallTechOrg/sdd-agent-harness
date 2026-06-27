"""Reusable dataset fixtures for the data-layer tests.

Builds small, deterministic CSV/xlsx files on disk so schema inference and
aggregation can be asserted against known-correct numbers. The large fixture is
shaped so a full-file aggregate differs from a head(50) sample — proving
aggregation runs over the whole file, not a truncated view.
"""
from __future__ import annotations

import os

import pandas as pd


def write_small_csv(dir_path: str) -> str:
    """A tiny mixed-type CSV: string, number, date columns.

    region   sales   date
    West     100     2024-01-01
    East     200     2024-01-02
    West     300     2024-02-01
    East     400     2024-02-02
    North    500     2024-03-01
    """
    df = pd.DataFrame(
        {
            "region": ["West", "East", "West", "East", "North"],
            "sales": [100, 200, 300, 400, 500],
            "date": [
                "2024-01-01",
                "2024-01-02",
                "2024-02-01",
                "2024-02-02",
                "2024-03-01",
            ],
        }
    )
    path = os.path.join(dir_path, "small.csv")
    df.to_csv(path, index=False)
    return path


def write_small_xlsx(dir_path: str) -> str:
    """Same shape as the small CSV, but as a real .xlsx (first sheet)."""
    df = pd.DataFrame(
        {
            "region": ["West", "East", "West", "East", "North"],
            "sales": [100, 200, 300, 400, 500],
            "date": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-02",
                    "2024-02-01",
                    "2024-02-02",
                    "2024-03-01",
                ]
            ),
        }
    )
    path = os.path.join(dir_path, "small.xlsx")
    df.to_excel(path, index=False, engine="openpyxl")
    return path


# Large fixture parameters — chosen to satisfy the privacy-test reuse contract:
# >= 500 rows and >= 12 distinct group keys.
LARGE_ROWS = 600
LARGE_GROUPS = 15


def write_large_csv(dir_path: str) -> tuple[str, dict]:
    """A >=500-row, >=12-group CSV with a known per-group sum.

    Returns (path, expected) where expected carries the full-file sums so tests
    can assert exact numbers AND that a head(50) sample sum differs.

    Construction: row i belongs to group f"g{i % LARGE_GROUPS}" and carries
    amount = (i % LARGE_GROUPS) + 1. This makes per-group sums deterministic and
    guarantees the head(50) sample (only groups g0..g4 in the first 50 rows when
    ordered) under-counts the full-file total for most groups.
    """
    regions = [f"g{i % LARGE_GROUPS}" for i in range(LARGE_ROWS)]
    amounts = [(i % LARGE_GROUPS) + 1 for i in range(LARGE_ROWS)]
    df = pd.DataFrame({"region": regions, "amount": amounts})

    path = os.path.join(dir_path, "large.csv")
    df.to_csv(path, index=False)

    full_sum_by_group = df.groupby("region")["amount"].sum().to_dict()
    sample_sum_by_group = (
        df.head(50).groupby("region")["amount"].sum().to_dict()
    )
    expected = {
        "rows": LARGE_ROWS,
        "groups": LARGE_GROUPS,
        "full_sum_by_group": {k: int(v) for k, v in full_sum_by_group.items()},
        "sample_sum_by_group": {k: int(v) for k, v in sample_sum_by_group.items()},
        "full_total": int(df["amount"].sum()),
        "sample_total": int(df.head(50)["amount"].sum()),
    }
    return path, expected
