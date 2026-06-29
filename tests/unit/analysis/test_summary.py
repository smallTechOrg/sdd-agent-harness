"""Unit tests for summarize_result — faithful formatting, numeric right-align."""
from analysis.summary import summarize_result


def test_columns_typed_and_aligned():
    rows = [
        {"region": "North", "total": 1210.0},
        {"region": "South", "total": 665.0},
    ]
    out = summarize_result(rows)
    assert out is not None
    cols = {c["name"]: c for c in out["columns"]}
    assert cols["region"]["type"] == "text"
    assert cols["region"]["align"] == "left"
    assert cols["total"]["type"] == "number"
    assert cols["total"]["align"] == "right"


def test_values_preserved_no_alteration():
    rows = [{"region": "North", "total": 1210}, {"region": "South", "total": 665}]
    out = summarize_result(rows)
    # Integers pass through faithfully; row order preserved.
    assert out["rows"] == [["North", 1210], ["South", 665]]


def test_float_rounding_is_display_only_faithful():
    # A long float rounds to <=4 dp for display but stays faithful.
    rows = [{"avg": 12.3456789}]
    out = summarize_result(rows)
    assert out["rows"][0][0] == 12.3457
    # An integer-valued float is preserved exactly.
    rows2 = [{"x": 250.0}]
    assert summarize_result(rows2)["rows"][0][0] == 250.0


def test_multi_row_shape():
    rows = [{"a": 1}, {"a": 2}, {"a": 3}]
    out = summarize_result(rows)
    assert len(out["rows"]) == 3
    assert out["columns"][0]["align"] == "right"


def test_empty_result_is_none():
    assert summarize_result([]) is None
    assert summarize_result(None) is None


def test_null_cells_preserved():
    rows = [{"region": "North", "total": None}]
    out = summarize_result(rows)
    assert out["rows"][0] == ["North", None]
