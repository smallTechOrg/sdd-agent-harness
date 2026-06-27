"""Unit tests for the read-only SQL guard.

The guard is a hard privacy/safety boundary: only a single read-only SELECT
(or WITH ... SELECT) may ever reach DuckDB. Everything else is rejected
*before* execution.
"""
import pytest

from analytics.sql_guard import is_read_only_select, assert_read_only_select


# --- accepted: single read-only statements -------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT region, SUM(amount) AS total FROM sales GROUP BY region",
        "select * from sales",
        "  SELECT 1  ",
        "SELECT * FROM sales WHERE region = 'North' ORDER BY amount DESC LIMIT 10",
        "WITH r AS (SELECT region, amount FROM sales) SELECT region, SUM(amount) FROM r GROUP BY region",
        "-- a leading comment\nSELECT * FROM sales",
        "/* block comment */ SELECT region FROM sales",
        "SELECT region FROM sales;",  # single trailing semicolon is fine
        "SELECT region FROM sales ;  ",  # trailing semicolon + whitespace
    ],
)
def test_accepts_read_only_selects(sql):
    assert is_read_only_select(sql) is True


# --- rejected: DDL / DML / non-SELECT ------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sales",
        "INSERT INTO sales VALUES (1, '2024-01-01', 'North', 'Widget', 1, 9.99)",
        "UPDATE sales SET amount = 0",
        "DELETE FROM sales",
        "ALTER TABLE sales ADD COLUMN x INT",
        "CREATE TABLE evil (id INT)",
        "CREATE TABLE evil AS SELECT * FROM sales",
        "ATTACH 'other.db' AS o",
        "COPY sales TO 'out.csv'",
        "PRAGMA database_list",
        "INSTALL httpfs",
        "LOAD httpfs",
        "TRUNCATE sales",
        "REPLACE INTO sales VALUES (1)",
        "",
        "   ",
        "EXPLAIN SELECT * FROM sales",  # not a plain SELECT entrypoint
        "WITH x AS (DELETE FROM sales RETURNING *) SELECT * FROM x",  # DML hidden in CTE
    ],
)
def test_rejects_non_selects(sql):
    assert is_read_only_select(sql) is False


# --- rejected: multi-statement injection ---------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DELETE FROM sales",
        "SELECT * FROM sales; DROP TABLE sales",
        "SELECT * FROM sales;SELECT * FROM sales",
        "SELECT 1; -- trailing\nINSERT INTO sales VALUES (1)",
    ],
)
def test_rejects_multi_statement(sql):
    assert is_read_only_select(sql) is False


# --- rejected: comment-obfuscated injections -----------------------------

def test_rejects_comment_obfuscated_dml():
    # A real second statement disguised after a comment.
    assert is_read_only_select("SELECT 1 /* sneaky */ ; DROP TABLE sales") is False


def test_comment_only_keyword_is_not_a_real_statement():
    # The word DROP only appears inside a comment, not as a statement -> allowed.
    assert is_read_only_select("SELECT region FROM sales -- DROP TABLE sales") is True


# --- the raising variant -------------------------------------------------

def test_assert_passes_for_select():
    # Should not raise.
    assert_read_only_select("SELECT * FROM sales")


def test_assert_raises_for_non_select():
    with pytest.raises(ValueError):
        assert_read_only_select("DROP TABLE sales")
