"""Guardrails (action-safety) — the read-only SQL boundary (harness/patterns/guardrails-and-hitl.md).

`run_sql` is gated to read-only queries. Defense in depth: this deterministic statement allowlist runs
BEFORE execution (clean refusal message the model can recover from), and the DuckDB connection is opened
read_only=True (the hard engine-level guarantee). A write can't fire even from a force-finalize or malformed
model output.
"""
import re

ALLOWED_LEADING = {
    "select", "with", "from", "table", "describe", "explain", "show", "pivot", "summarize", "values",
}
FORBIDDEN = {
    "insert", "update", "delete", "drop", "alter", "create", "replace", "truncate", "attach", "detach",
    "copy", "install", "load", "pragma", "set", "export", "import", "call", "vacuum", "checkpoint", "reset",
}


def _strip(sql: str) -> str:
    s = re.sub(r"--[^\n]*", " ", sql)                 # line comments
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)      # block comments
    return s.strip()


def validate_read_only(sql: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=False with a human reason when the statement is not a single read-only query."""
    s = _strip(sql)
    if not s:
        return False, "empty query"
    core = s.rstrip(";").strip()
    if ";" in core:
        return False, "only a single statement is allowed"
    lead = re.match(r"[a-zA-Z]+", core)
    if not lead or lead.group(0).lower() not in ALLOWED_LEADING:
        allowed = ", ".join(sorted(ALLOWED_LEADING))
        return False, f"only read-only queries are allowed (must start with one of: {allowed})"
    # scan for write/DDL keywords, ignoring string literals and quoted identifiers
    masked = re.sub(r"'(?:[^']|'')*'", " ", core)
    masked = re.sub(r'"(?:[^"]|"")*"', " ", masked)
    hit = {t for t in re.findall(r"[a-zA-Z_]+", masked.lower())} & FORBIDDEN
    if hit:
        return False, f"write/DDL keyword not allowed: {', '.join(sorted(hit))}"
    return True, ""
