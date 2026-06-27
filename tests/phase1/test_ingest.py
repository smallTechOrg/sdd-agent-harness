from pathlib import Path

import pytest

from datasets import profile as profile_mod
from datasets.profile import build_profile
from datasets.storage import load_file, save_file

FIXTURE = Path(__file__).parent / "fixtures" / "employees.csv"
FIXTURE_ROWS = 7
FIXTURE_COLS = ["name", "department", "salary"]


@pytest.fixture(autouse=True)
def _uploads_under_tmp(tmp_path, monkeypatch):
    """Redirect the upload dir into tmp so tests never write into the real data/."""
    import datasets.storage as storage_mod

    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(storage_mod, "UPLOAD_DIR", upload_dir)
    return upload_dir


def test_save_file_writes_under_uploads(_uploads_under_tmp):
    content = FIXTURE.read_bytes()
    path = save_file("ds-123", "csv", content)

    assert path == str(_uploads_under_tmp / "ds-123.csv")
    assert Path(path).exists()
    assert Path(path).read_bytes() == content
    # Lives under the uploads dir, not transmitted anywhere.
    assert _uploads_under_tmp in Path(path).parents


def test_save_then_load_roundtrip(_uploads_under_tmp):
    content = FIXTURE.read_bytes()
    path = save_file("ds-roundtrip", "csv", content)
    assert load_file(path) == content


def test_save_normalizes_extension(_uploads_under_tmp):
    path = save_file("ds-ext", ".CSV", b"a,b\n1,2\n")
    assert path.endswith("ds-ext.csv")


def test_build_profile_counts_and_columns(_uploads_under_tmp):
    path = save_file("ds-profile", "csv", FIXTURE.read_bytes())
    prof = build_profile(path)

    assert prof.row_count == FIXTURE_ROWS
    assert prof.column_count == len(FIXTURE_COLS)
    assert prof.columns == FIXTURE_COLS


def test_schema_summary_has_real_columns_and_dtypes(_uploads_under_tmp):
    path = save_file("ds-schema", "csv", FIXTURE.read_bytes())
    prof = build_profile(path)
    summary = prof.schema_summary

    names = [c.name for c in summary.columns]
    assert names == FIXTURE_COLS

    by_name = {c.name: c for c in summary.columns}
    # salary is numeric -> numeric dtype + numeric stats present
    assert "int" in by_name["salary"].dtype or "float" in by_name["salary"].dtype
    assert "mean" in by_name["salary"].stats
    assert "min" in by_name["salary"].stats
    assert "max" in by_name["salary"].stats
    # department is categorical/text -> non-numeric dtype + most_common stat
    dept_dtype = by_name["department"].dtype
    assert "object" in dept_dtype or "str" in dept_dtype
    assert "most_common" in by_name["department"].stats


def test_schema_summary_sample_is_bounded(_uploads_under_tmp):
    path = save_file("ds-bounded", "csv", FIXTURE.read_bytes())
    prof = build_profile(path, sample_rows=3)
    summary = prof.schema_summary

    assert summary.sample_row_count == 3
    assert len(summary.sample_rows) == 3
    # The sample never exceeds the dataset and is far smaller than the full frame.
    assert len(summary.sample_rows) <= prof.row_count
    # Sample rows carry the real column keys.
    assert set(summary.sample_rows[0].keys()) == set(FIXTURE_COLS)
    # Values are stringified (small + portable for the LLM payload).
    assert all(isinstance(v, str) for v in summary.sample_rows[0].values())


def test_default_sample_cap(_uploads_under_tmp):
    path = save_file("ds-default", "csv", FIXTURE.read_bytes())
    prof = build_profile(path)
    assert prof.schema_summary.sample_row_count == profile_mod.DEFAULT_SAMPLE_ROWS


def test_build_profile_raises_on_unparseable(_uploads_under_tmp):
    # A binary blob that pandas cannot read as CSV.
    path = save_file("ds-bad", "csv", b"\x00\x01\x02\xff\xfe garbage \x00")
    with pytest.raises(Exception):
        build_profile(path)
