from data_analyst.graph.nodes import _repair_table_names

CONTEXTS = [{"name": "fifa", "duckdb_table": "s1_fifa"}]


def test_repairs_bare_display_name():
    sql = "SELECT count(*) FROM fifa GROUP BY year"
    out = _repair_table_names(sql, CONTEXTS)
    assert '"s1_fifa"' in out
    assert " fifa " not in f" {out} "


def test_repairs_quoted_display_name():
    sql = 'SELECT * FROM "fifa"'
    out = _repair_table_names(sql, CONTEXTS)
    assert '"s1_fifa"' in out


def test_leaves_correct_table_untouched():
    sql = 'SELECT count(*) FROM "s1_fifa"'
    out = _repair_table_names(sql, CONTEXTS)
    assert out == sql


def test_does_not_touch_substring_columns():
    # a column literally named 'fifard' must not be partially rewritten
    sql = 'SELECT fifard FROM "s1_fifa"'
    out = _repair_table_names(sql, CONTEXTS)
    assert "fifard" in out
    assert '"s1_fifard"' not in out
