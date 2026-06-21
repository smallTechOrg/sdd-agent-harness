"""Read-only SQL guardrail (query-data EARS: a non-read-only statement is refused, no mutation).

Covers the action-safety boundary deterministically, independent of the live model's wording
(harness/patterns/guardrails-and-hitl.md).
"""
import pytest

from src.guardrails import validate_read_only


@pytest.mark.parametrize("sql", [
    "SELECT category, sum(amount) FROM sales GROUP BY category",
    "with c as (select 1 as x) select * from c",
    "DESCRIBE sales",
    "SELECT 'drop table x' AS note",        # forbidden word only inside a string literal — allowed
])
def test_read_only_allows_queries(sql):
    ok, reason = validate_read_only(sql)
    assert ok, f"should allow: {sql!r} ({reason})"


@pytest.mark.parametrize("sql", [
    "DROP TABLE sales",
    "DELETE FROM sales",
    "UPDATE sales SET amount = 0",
    "INSERT INTO sales VALUES (1)",
    "ALTER TABLE sales ADD COLUMN x INT",
    "ATTACH 'evil.db' AS e",
    "COPY sales TO 'out.csv'",
    "SELECT 1; DROP TABLE sales",           # multi-statement smuggling
    "PRAGMA database_list",
])
def test_read_only_refuses_writes(sql):
    ok, reason = validate_read_only(sql)
    assert not ok, f"should refuse: {sql!r}"
    assert reason                            # a human-readable reason is returned for the model to recover


def test_execute_sql_tool_refuses_write_without_touching_data():
    """The tool returns a refusal string (fail-soft), never executing the write."""
    from src.tools import execute_sql
    out = execute_sql.invoke({"dataset_id": "any", "sql": "DROP TABLE sales"})
    assert out.startswith("REFUSED")
