"""Schema inference tests — local pandas, no LLM, no DB."""
import os

import pytest

from data.schema import infer
from tests.fixtures.datasets import write_small_csv, write_small_xlsx


def test_infer_csv_dtypes_and_row_count(tmp_path):
    path = write_small_csv(str(tmp_path))
    result = infer(path)

    assert result["row_count"] == 5
    by_name = {c["name"]: c["dtype"] for c in result["columns"]}
    assert by_name == {"region": "string", "sales": "number", "date": "date"}
    # Column order is preserved from the file.
    assert [c["name"] for c in result["columns"]] == ["region", "sales", "date"]


def test_infer_xlsx_dtypes_and_row_count(tmp_path):
    path = write_small_xlsx(str(tmp_path))
    result = infer(path)

    assert result["row_count"] == 5
    by_name = {c["name"]: c["dtype"] for c in result["columns"]}
    assert by_name["region"] == "string"
    assert by_name["sales"] == "number"
    assert by_name["date"] == "date"


def test_infer_never_returns_rows(tmp_path):
    path = write_small_csv(str(tmp_path))
    result = infer(path)
    # The returned schema must carry ONLY columns + row_count — no row data.
    assert set(result.keys()) == {"columns", "row_count"}
    for col in result["columns"]:
        assert set(col.keys()) == {"name", "dtype"}


def test_infer_unsupported_extension_raises(tmp_path):
    bad = os.path.join(str(tmp_path), "data.txt")
    with open(bad, "w") as fh:
        fh.write("not,a,supported,file\n1,2,3,4\n")
    with pytest.raises(ValueError):
        infer(bad)


def test_infer_empty_file_raises(tmp_path):
    # A CSV with a header but no data rows.
    empty = os.path.join(str(tmp_path), "empty.csv")
    with open(empty, "w") as fh:
        fh.write("region,sales,date\n")
    with pytest.raises(ValueError):
        infer(empty)


def test_infer_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        infer(os.path.join(str(tmp_path), "nope.csv"))
