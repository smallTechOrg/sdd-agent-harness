"""Read-only single-SELECT guard.

This is a hard safety boundary: only one read-only statement that starts with
``SELECT`` (or ``WITH ... SELECT``) may ever be executed against DuckDB.
Anything else — DDL, DML, multi-statement injections, PRAGMA/ATTACH/COPY, etc.
— is rejected *before* execution.

The guard is intentionally conservative: when in doubt, reject.
"""
from __future__ import annotations

import re

# Keywords that must never appear as a statement we execute. Matched as whole
# words (case-insensitive) against the comment-stripped SQL.
_FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "ATTACH",
    "DETACH",
    "COPY",
    "PRAGMA",
    "INSTALL",
    "LOAD",
    "REPLACE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "CALL",
    "EXPORT",
    "IMPORT",
    "SET",
    "RESET",
    "MERGE",
    "UPSERT",
)

_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)


def _strip_comments(sql: str) -> str:
    """Remove -- line comments and /* block */ comments."""
    # Block comments (non-greedy, across newlines).
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Line comments to end of line.
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def is_read_only_select(sql: str) -> bool:
    """Return True iff *sql* is a single read-only SELECT/WITH statement."""
    if not sql or not sql.strip():
        return False

    cleaned = _strip_comments(sql).strip()

    # Drop a single trailing semicolon (a normal terminator).
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()

    if not cleaned:
        return False

    # Any remaining ';' implies a second statement -> reject.
    if ";" in cleaned:
        return False

    # Must begin with SELECT or WITH (CTE feeding a SELECT).
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        return False

    # No DDL/DML keyword may appear anywhere (covers DML hidden inside a CTE).
    if _FORBIDDEN_RE.search(cleaned):
        return False

    return True


def assert_read_only_select(sql: str) -> str:
    """Validate *sql*; return it unchanged, or raise ``ValueError``."""
    if not is_read_only_select(sql):
        raise ValueError(
            "Rejected SQL: only a single read-only SELECT (or WITH ... SELECT) "
            "may be executed."
        )
    return sql
