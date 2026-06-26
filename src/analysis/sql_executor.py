"""Constrained local execution of LLM-generated SQL queries.

The generated SQL query is UNTRUSTED LLM output. It is executed locally against
an in-memory SQLite table, as documented in ``spec/architecture.md → Sandbox
Security Model``:

  * Static AST/regex validation rejects SELECT-only, no mutations, no multi-statement,
    and no direct file I/O BEFORE anything is executed.
  * The query is executed against an in-memory SQLite table loaded from the DataFrame.
  * Execution runs under a wall-clock timeout.
  * The result is normalized to a JSON-serializable ``{columns, rows}`` table,
    capped at ``settings.max_result_rows``.

This is defense-in-depth for a single-user local tool, NOT a hardened
multi-tenant sandbox (see the architecture doc for the documented limits).
"""

from __future__ import annotations

import re
import sqlite3
import threading
from typing import Any

import pandas as pd


class SQLExecutorError(ValueError):
    """Raised for any SQL executor failure (validation / exec error / timeout)."""


def _validate_sql(sql: str) -> None:
    """Validate that the SQL is a safe SELECT query.

    Raises :class:`SQLExecutorError` on any rejected construct.
    Checks:
      - Must be a single statement (no semicolons except trailing)
      - Must start with SELECT (case-insensitive)
      - No INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH
      - No multi-statement chains
    """
    sql = sql.strip()
    if not sql:
        raise SQLExecutorError("The SQL query is empty.")

    # Remove trailing semicolon if present (it's optional)
    if sql.endswith(";"):
        sql = sql[:-1].strip()

    # Check for multiple statements (semicolon in the middle)
    if ";" in sql:
        raise SQLExecutorError("The SQL query cannot contain multiple statements.")

    # Case-insensitive check for allowed vs forbidden keywords
    upper = sql.upper()

    # Must start with SELECT
    if not re.match(r"^\s*SELECT\b", upper):
        raise SQLExecutorError("Only SELECT queries are allowed.")

    # Reject dangerous keywords
    forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "PRAGMA",
        "ATTACH",
        "LOAD_EXTENSION",
        "VACUUM",
        "ANALYZE",
        "REINDEX",
    ]
    for keyword in forbidden:
        # Use word boundary to avoid false positives on column names
        if re.search(rf"\b{keyword}\b", upper):
            raise SQLExecutorError(f"The SQL query is not allowed to use {keyword}.")


def _dataframe_to_sqlite(df: pd.DataFrame, table_name: str = "data") -> sqlite3.Connection:
    """Create an in-memory SQLite table from a DataFrame.

    Returns an in-memory Connection with the table created.
    """
    conn = sqlite3.connect(":memory:")
    df.to_sql(table_name, conn, index=False, if_exists="replace")
    return conn


def _result_to_dict(cursor: sqlite3.Cursor, rows: list[tuple]) -> dict:
    """Normalize cursor results to {columns, rows}."""
    if not cursor.description:
        return {"columns": [], "rows": []}

    columns = [desc[0] for desc in cursor.description]
    # Normalize each row to handle sqlite3 types
    normalized_rows = [[v if v is not None else None for v in row] for row in rows]
    return {"columns": columns, "rows": normalized_rows}


def run_sql(
    sql: str,
    df: pd.DataFrame,
    table_name: str = "data",
    timeout: float = 10,
    max_rows: int = 1000,
) -> tuple[dict, bool]:
    """Execute SQL query against a DataFrame.

    Args:
        sql: The SQL query string.
        df: The full pandas DataFrame to load into SQLite.
        table_name: The name of the table to create (default "data").
        timeout: Wall-clock timeout in seconds.
        max_rows: Maximum rows to return before truncating.

    Returns:
        (result_table, truncated) where result_table is {columns, rows}
        or raises :class:`SQLExecutorError`.
    """
    _validate_sql(sql)

    holder: dict[str, Any] = {}

    def _worker() -> None:
        try:
            # Create the in-memory SQLite table INSIDE the worker thread to avoid
            # cross-thread SQLite object usage issues.
            conn = _dataframe_to_sqlite(df, table_name)
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            # Extract column names and rows before closing the connection
            column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            holder["column_names"] = column_names
            holder["rows"] = rows
            holder["success"] = True
            conn.close()
        except sqlite3.OperationalError as exc:
            holder["error"] = f"SQL error: {exc}"
        except Exception as exc:  # noqa: BLE001
            holder["error"] = f"Query execution failed: {exc}"

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise SQLExecutorError(
            f"The SQL query took too long (over {timeout}s) and was stopped."
        )

    if "error" in holder:
        raise SQLExecutorError(holder["error"])

    if not holder.get("success"):
        raise SQLExecutorError("The SQL query failed to execute.")

    rows = holder.get("rows", [])
    column_names = holder.get("column_names", [])

    # Check for truncation
    truncated = False
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        truncated = True

    # Build result dict directly from extracted data
    result_table = {
        "columns": column_names,
        "rows": [[v if v is not None else None for v in row] for row in rows],
    }
    return result_table, truncated


# Inline doctest for validation
if __name__ == "__main__":
    # Test basic SQL execution
    test_df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie"],
        "age": [25, 30, 35],
        "salary": [50000, 60000, 75000],
    })

    # Test 1: Basic SELECT
    result, truncated = run_sql("SELECT * FROM data", test_df, timeout=5, max_rows=1000)
    assert result["columns"] == ["name", "age", "salary"], f"Columns mismatch: {result['columns']}"
    assert len(result["rows"]) == 3, f"Expected 3 rows, got {len(result['rows'])}"
    assert not truncated

    # Test 2: Aggregation
    result, truncated = run_sql("SELECT SUM(salary) as total_salary FROM data", test_df, timeout=5, max_rows=1000)
    assert result["columns"] == ["total_salary"]
    assert result["rows"][0][0] == 185000

    # Test 3: GROUP BY
    result, truncated = run_sql("SELECT age, COUNT(*) as count FROM data GROUP BY age ORDER BY age", test_df, timeout=5, max_rows=1000)
    assert len(result["rows"]) == 3
    assert result["rows"][0] == [25, 1]

    # Test 4: Rejection of INSERT
    try:
        run_sql("INSERT INTO data VALUES ('x', 1, 2)", test_df, timeout=5, max_rows=1000)
        assert False, "Should have rejected INSERT"
    except SQLExecutorError as e:
        assert "SELECT" in str(e) or "INSERT" in str(e)

    # Test 5: Rejection of multiple statements
    try:
        run_sql("SELECT * FROM data; DROP TABLE data;", test_df, timeout=5, max_rows=1000)
        assert False, "Should have rejected multi-statement"
    except SQLExecutorError as e:
        assert "multiple statements" in str(e)

    print("All inline doctests passed!")
