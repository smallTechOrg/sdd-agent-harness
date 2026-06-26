"""Unit tests for the SQL safety guard — no LLM or DB calls."""
import pytest
from graph.nodes import is_sql_safe


@pytest.mark.parametrize("sql", [
    "INSERT INTO foo VALUES (1)",
    "UPDATE foo SET x=1",
    "DELETE FROM foo",
    "DROP TABLE foo",
    "CREATE TABLE foo (id INTEGER)",
    "ALTER TABLE foo ADD COLUMN x TEXT",
    "TRUNCATE TABLE foo",
])
def test_blocked_keywords(sql):
    assert is_sql_safe(sql) is False


@pytest.mark.parametrize("sql", [
    "SELECT * FROM foo",
    "SELECT id, name FROM sales WHERE revenue > 100",
    "SELECT COUNT(*) FROM orders GROUP BY product",
    "SELECT a, b FROM t ORDER BY b DESC LIMIT 10",
    "select * from foo",  # lowercase
    "SELECT name, SUM(revenue) FROM sales GROUP BY name",
])
def test_valid_select_passes(sql):
    assert is_sql_safe(sql) is True


def test_case_insensitive_insert():
    assert is_sql_safe("insert into foo values (1)") is False


def test_case_insensitive_drop():
    assert is_sql_safe("drop table foo") is False


def test_embedded_keyword_in_column_name_blocked():
    # "dropship" contains "drop" but with word boundary check should be safe
    # Actually \b matches word boundary so "dropship" should NOT match DROP
    assert is_sql_safe("SELECT dropship_id FROM orders") is True


def test_select_with_subquery():
    sql = "SELECT * FROM (SELECT id FROM foo WHERE id > 0)"
    assert is_sql_safe(sql) is True
