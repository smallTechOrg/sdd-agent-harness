"""Token-economy guard + SQL-validation unit tests (no LLM key, no DB)."""
import pytest

from graph.nodes import (
    build_sql_prompt,
    build_narrate_prompt,
    validate_sql,
    _strip_sql_fences,
)


def _schema_ctx(n_samples: int) -> dict:
    return {
        "table_name": "dataset_ab12",
        "columns": [
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
        ],
        "sample_rows": [[f"R{i}", float(i)] for i in range(n_samples)],
        "aggregates": {},
    }


@pytest.mark.parametrize("max_rows", [1, 3, 5])
def test_sql_prompt_never_exceeds_max_sample_rows(max_rows):
    # 50 candidate rows available, but only max_rows may appear.
    ctx = _schema_ctx(50)
    prompt = build_sql_prompt(ctx, "total sales by region", max_rows)
    # Count rendered data rows: each sample row contains the "R<i> | <i>.0" form.
    data_lines = [ln for ln in prompt.splitlines() if ln.strip().startswith("R")]
    assert len(data_lines) <= max_rows
    assert len(data_lines) == max_rows  # exactly capped when plenty available


def test_sql_prompt_with_fewer_samples_than_cap():
    ctx = _schema_ctx(2)
    prompt = build_sql_prompt(ctx, "q", 5)
    data_lines = [ln for ln in prompt.splitlines() if ln.strip().startswith("R")]
    assert len(data_lines) == 2


def test_narrate_prompt_caps_result_preview():
    rows = [[f"row{i}", i] for i in range(100)]
    prompt = build_narrate_prompt(
        "q", "SELECT * FROM t", ["a", "b"], rows, row_count=100, preview_rows=10
    )
    data_lines = [ln for ln in prompt.splitlines() if ln.strip().startswith("row")]
    assert len(data_lines) <= 10
    assert "Total result rows: 100" in prompt


def test_strip_sql_fences():
    assert _strip_sql_fences("```sql\nSELECT 1\n```") == "SELECT 1"
    assert _strip_sql_fences("```\nSELECT 1\n```") == "SELECT 1"
    assert _strip_sql_fences("SELECT 1;") == "SELECT 1"
    assert _strip_sql_fences("  SELECT 1  ") == "SELECT 1"


# --------------------------- SQL validation --------------------------------- #
_COLS = ["region", "amount"]
_TABLE = "dataset_ab12"


def test_validate_accepts_clean_select():
    validate_sql(
        "SELECT region, SUM(amount) AS total FROM dataset_ab12 GROUP BY region ORDER BY total DESC",
        _COLS,
        _TABLE,
    )


def test_validate_rejects_non_select():
    with pytest.raises(ValueError):
        validate_sql("DELETE FROM dataset_ab12", _COLS, _TABLE)


def test_validate_rejects_write_keyword_in_select():
    with pytest.raises(ValueError):
        validate_sql("SELECT * FROM dataset_ab12; DROP TABLE dataset_ab12", _COLS, _TABLE)


def test_validate_rejects_multiple_statements():
    with pytest.raises(ValueError):
        validate_sql("SELECT 1 FROM dataset_ab12; SELECT 2 FROM dataset_ab12", _COLS, _TABLE)


def test_validate_rejects_unknown_column():
    with pytest.raises(ValueError):
        validate_sql("SELECT bogus_col FROM dataset_ab12", _COLS, _TABLE)


def test_validate_rejects_missing_table_reference():
    with pytest.raises(ValueError):
        validate_sql("SELECT region FROM other_table", _COLS, _TABLE)


def test_validate_allows_with_cte():
    validate_sql(
        "WITH t AS (SELECT region, amount FROM dataset_ab12) SELECT region FROM t",
        _COLS,
        _TABLE,
    )
