"""Unit tests for the local-data execution engine (src/execution).

Covers:
- profile shape correctness + JSON-serializability + missing/row counts
- the LARGE-FILE / PRIVACY gate: full-file aggregates differ from a 20-row
  sample, the sandbox computes the FULL answer, and the profile sample is
  bounded by the cap regardless of file size
- sandbox safety: import/open/eval are neutralized, not crashes
- result normalization for scalar / Series / DataFrame
- wall-clock timeout
- error transparency: real traceback captured, not raised
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from execution.profile import (
    DEFAULT_SAMPLE_ROWS,
    MalformedCSVError,
    load_csv,
    profile_csv,
    profile_dataframe,
)
from execution.sandbox import (
    RESULT_TABLE_ROW_CAP,
    ExecResult,
    execute_pandas,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SMALL_CSV = FIXTURES / "small_sales.csv"
LARGE_CSV = FIXTURES / "large_sales.csv"


# --------------------------------------------------------------------------- #
# profile shape correctness
# --------------------------------------------------------------------------- #

def test_small_csv_fixture_exists():
    assert SMALL_CSV.exists(), f"missing fixture {SMALL_CSV}"
    assert LARGE_CSV.exists(), f"missing fixture {LARGE_CSV}"


def test_profile_row_count_and_top_level_shape():
    profile = profile_csv(str(SMALL_CSV), sample_rows=DEFAULT_SAMPLE_ROWS)
    assert set(profile.keys()) == {"row_count", "columns", "sample_rows"}
    assert profile["row_count"] == 6
    assert isinstance(profile["columns"], list)
    assert isinstance(profile["sample_rows"], list)


def _col(profile: dict, name: str) -> dict:
    for c in profile["columns"]:
        if c["name"] == name:
            return c
    raise AssertionError(f"column {name} not found in profile")


def test_numeric_column_has_min_max_mean():
    profile = profile_dataframe(load_csv(str(SMALL_CSV)))
    revenue = _col(profile, "revenue")
    # revenue values: 100, 200, NaN, 400, 150, 50 -> 5 present, 1 missing
    assert revenue["dtype"].startswith("float")
    assert revenue["missing"] == 1
    assert revenue["min"] == 50.0
    assert revenue["max"] == 400.0
    assert revenue["mean"] == pytest.approx((100 + 200 + 400 + 150 + 50) / 5)
    # numeric columns must NOT carry the object-only keys
    assert "distinct" not in revenue
    assert "sample_values" not in revenue


def test_object_column_has_distinct_and_sample_values():
    profile = profile_dataframe(load_csv(str(SMALL_CSV)))
    region = _col(profile, "region")
    # Text columns are profiled with distinct + sample_values. The exact dtype
    # literal is pandas-version-dependent ("object" on pandas 2.x, "str" on
    # pandas 3.x) so we accept either rather than pinning a version.
    assert region["dtype"] in ("object", "str")
    # region: North, South, East, West, North, None -> 1 missing, 4 distinct
    assert region["missing"] == 1
    assert region["distinct"] == 4
    assert isinstance(region["sample_values"], list)
    assert "North" in region["sample_values"]
    # None must not appear among sample values
    assert None not in region["sample_values"]
    # object columns must NOT carry numeric-only keys
    assert "min" not in region
    assert "mean" not in region


def test_missing_counts_correct_across_columns():
    profile = profile_dataframe(load_csv(str(SMALL_CSV)))
    assert _col(profile, "region")["missing"] == 1
    assert _col(profile, "revenue")["missing"] == 1
    assert _col(profile, "product")["missing"] == 0
    assert _col(profile, "units")["missing"] == 0


def test_profile_is_json_serializable():
    profile = profile_dataframe(load_csv(str(SMALL_CSV)))
    # Must round-trip through JSON without error (no numpy scalars, no NaN).
    dumped = json.dumps(profile)
    reloaded = json.loads(dumped)
    assert reloaded["row_count"] == 6


def test_nan_in_sample_rows_becomes_null():
    profile = profile_dataframe(load_csv(str(SMALL_CSV)), sample_rows=10)
    # Row index 2 has revenue NaN; row index 5 has region None.
    revenue_values = [r["revenue"] for r in profile["sample_rows"]]
    region_values = [r["region"] for r in profile["sample_rows"]]
    assert None in revenue_values  # NaN -> null
    assert None in region_values   # None preserved as null
    # And the whole thing is JSON-safe.
    json.dumps(profile["sample_rows"])


def test_all_numeric_missing_column_yields_null_stats():
    df = pd.DataFrame({"x": [np.nan, np.nan], "y": [1, 2]})
    profile = profile_dataframe(df)
    x = _col(profile, "x")
    assert x["missing"] == 2
    assert x["min"] is None and x["max"] is None and x["mean"] is None


# --------------------------------------------------------------------------- #
# LARGE-FILE / PRIVACY gate  (REQUIRED)
# --------------------------------------------------------------------------- #

def test_sample_rows_bounded_by_cap_regardless_of_file_size():
    """The privacy bound: the profile sample never exceeds the cap, even for a
    60k-row file."""
    profile = profile_csv(str(LARGE_CSV), sample_rows=20)
    assert profile["row_count"] >= 50_000  # it really is the full large file
    assert len(profile["sample_rows"]) <= 20
    # A different (smaller) cap is also honored.
    profile5 = profile_csv(str(LARGE_CSV), sample_rows=5)
    assert len(profile5["sample_rows"]) == 5


def test_full_file_aggregate_differs_from_sample_and_sandbox_computes_full():
    """The data-processing correctness gate: executing the generated pandas
    code on the FULL dataframe yields the full-file answer, which is provably
    DIFFERENT from what a 20-row sample would produce."""
    df = load_csv(str(LARGE_CSV))
    sample_df = df.head(20)

    # Ground truth computed directly.
    full_truth = df.groupby("region")["revenue"].mean()
    sample_truth = sample_df.groupby("region")["revenue"].mean()

    # The sample sees only one region ("North") with tiny revenue; the full
    # file sees 5 regions with large revenue. They MUST differ — otherwise the
    # fixture is not exercising the privacy/full-data path.
    assert df["region"].nunique() > sample_df["region"].nunique()
    assert full_truth["North"] != pytest.approx(sample_truth["North"])
    assert abs(full_truth["North"] - sample_truth["North"]) > 100

    # Now the sandbox, run on the FULL df, must reproduce the FULL answer.
    code = "result = df.groupby('region')['revenue'].mean()"
    res = execute_pandas(code, df, timeout_s=10)
    assert res.error is None, res.error
    assert res.key_numbers is not None
    # All 5 regions present with the FULL-file means (not the sample's single
    # under-counted region).
    assert set(res.key_numbers.keys()) == set(full_truth.index.astype(str))
    assert res.key_numbers["North"] == pytest.approx(full_truth["North"])
    # And emphatically NOT the misleading sample value.
    assert res.key_numbers["North"] != pytest.approx(sample_truth["North"])


def test_full_file_rowcount_matches_loaded_frame():
    df = load_csv(str(LARGE_CSV))
    code = "result = len(df)"
    res = execute_pandas(code, df, timeout_s=10)
    assert res.error is None, res.error
    assert res.key_numbers == {"result": len(df)}
    assert res.key_numbers["result"] >= 50_000


# --------------------------------------------------------------------------- #
# sandbox safety
# --------------------------------------------------------------------------- #

@pytest.fixture
def df():
    return pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "g": ["a", "a", "b", "b"]})


def test_import_is_blocked_not_crash(df):
    res = execute_pandas("import os\nresult = os.getcwd()", df, timeout_s=5)
    assert res.error is not None
    assert "result" not in (res.key_numbers or {})


def test_open_is_blocked(df):
    res = execute_pandas("result = open('/etc/passwd').read()", df, timeout_s=5)
    assert res.error is not None
    assert res.key_numbers is None


def test_eval_and_exec_are_blocked(df):
    res_eval = execute_pandas("result = eval('1+1')", df, timeout_s=5)
    assert res_eval.error is not None
    res_exec = execute_pandas("exec('x=1')\nresult = 1", df, timeout_s=5)
    assert res_exec.error is not None


def test_dunder_import_is_blocked(df):
    res = execute_pandas("result = __import__('os').getcwd()", df, timeout_s=5)
    assert res.error is not None


def test_safe_builtins_still_available(df):
    res = execute_pandas("result = len(df) + max([1, 2, 3])", df, timeout_s=5)
    assert res.error is None, res.error
    assert res.key_numbers == {"result": 4 + 3}


# --------------------------------------------------------------------------- #
# result normalization
# --------------------------------------------------------------------------- #

def test_scalar_result_normalizes_to_key_numbers(df):
    res = execute_pandas("result = df['x'].mean()", df, timeout_s=5)
    assert res.error is None, res.error
    assert res.key_numbers == {"result": pytest.approx(2.5)}
    # scalar -> JSON-safe (a plain float, not numpy)
    json.dumps(res.key_numbers)


def test_series_result_normalizes_to_key_numbers_and_table(df):
    res = execute_pandas("result = df.groupby('g')['x'].sum()", df, timeout_s=5)
    assert res.error is None, res.error
    assert res.key_numbers == {"a": pytest.approx(3.0), "b": pytest.approx(7.0)}
    assert res.result_table is not None
    assert {"key": "a", "value": pytest.approx(3.0)} in res.result_table
    json.dumps({"key_numbers": res.key_numbers, "result_table": res.result_table})


def test_dataframe_result_normalizes_to_result_table(df):
    code = "result = df.groupby('g', as_index=False)['x'].sum()"
    res = execute_pandas(code, df, timeout_s=5)
    assert res.error is None, res.error
    assert isinstance(res.result_table, list)
    assert len(res.result_table) == 2
    # rows are JSON-serializable dicts keyed by column name
    cols = set(res.result_table[0].keys())
    assert cols == {"g", "x"}
    json.dumps(res.result_table)


def test_dataframe_result_table_capped(df):
    big = pd.DataFrame({"v": list(range(RESULT_TABLE_ROW_CAP + 50))})
    res = execute_pandas("result = df", big, timeout_s=5)
    assert res.error is None, res.error
    assert isinstance(res.result_table, list)
    assert len(res.result_table) == RESULT_TABLE_ROW_CAP


def test_missing_result_variable_is_reported(df):
    res = execute_pandas("x = df['x'].sum()", df, timeout_s=5)
    assert res.error is not None
    assert "result" in res.error.lower()


# --------------------------------------------------------------------------- #
# timeout
# --------------------------------------------------------------------------- #

def test_timeout_returns_error_not_hang(df):
    # A deliberately slow pure-python loop; 1s timeout keeps the test fast.
    slow = "total = 0\nfor i in range(10**12):\n    total += i\nresult = total"
    res = execute_pandas(slow, df, timeout_s=1)
    assert res.error is not None
    assert "exceeded" in res.error.lower()
    assert "1s" in res.error


# --------------------------------------------------------------------------- #
# error transparency
# --------------------------------------------------------------------------- #

def test_missing_column_returns_real_keyerror_with_traceback(df):
    res = execute_pandas("result = df['does_not_exist'].mean()", df, timeout_s=5)
    assert res.error is not None
    assert "does_not_exist" in res.error
    assert res.traceback is not None
    # The traceback points at the generated code, not the sandbox internals.
    assert "<generated>" in res.traceback
    assert "sandbox.py" not in res.traceback


def test_syntax_error_is_captured_not_raised(df):
    res = execute_pandas("result = df[", df, timeout_s=5)
    assert res.error is not None
    assert "SyntaxError" in res.error


def test_runtime_error_does_not_raise(df):
    # ZeroDivisionError inside generated code -> captured, never propagated.
    res = execute_pandas("result = 1 / 0", df, timeout_s=5)
    assert res.error is not None
    assert "ZeroDivisionError" in res.error
    assert res.traceback is not None


# --------------------------------------------------------------------------- #
# load_csv error handling
# --------------------------------------------------------------------------- #

def test_load_csv_malformed_raises_clear_error(tmp_path):
    bad = tmp_path / "bad.csv"
    # Ragged rows that pandas' C parser rejects.
    bad.write_text('a,b,c\n1,2,3\n4,5,6,7,8,9,10\n', encoding="utf-8")
    with pytest.raises(MalformedCSVError):
        load_csv(str(bad))


def test_profile_csv_propagates_malformed(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(MalformedCSVError):
        profile_csv(str(empty))


def test_execresult_default_shape():
    r = ExecResult()
    assert r.result_table is None
    assert r.key_numbers is None
    assert r.error is None
    assert r.traceback is None
