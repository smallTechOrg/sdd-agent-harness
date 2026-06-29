"""Deterministic summary-table formatting over an aggregate result.

Privacy boundary: operates ONLY on the aggregate result rows the answer node
already received — never raw source rows, never an LLM call. Formatting is
display-only: numeric columns are right-aligned and floats are rounded for
display, but the rounding NEVER alters a value's correctness — an integer or a
value already short enough is passed through faithfully.

Output shape::

    {"columns": [{"name", "type": "number"|"text", "align": "right"|"left"}],
     "rows": [[...], [...]]}

Returns ``None`` for an empty result.
"""
from __future__ import annotations

# Round display floats to at most this many decimal places. Only applied when it
# does not lose precision that matters — integers and already-short floats are
# left exactly as-is.
_DISPLAY_DECIMALS = 4


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _column_is_numeric(values: list) -> bool:
    seen = False
    for v in values:
        if v is None:
            continue
        seen = True
        if not _is_number(v):
            return False
    return seen


def _format_value(value):
    """Format a single cell for display without altering its true value.

    Floats are rounded to ``_DISPLAY_DECIMALS`` places for display only; if the
    value is already an integer-valued float or short, it is returned faithfully.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        rounded = round(value, _DISPLAY_DECIMALS)
        # Preserve integer-valued floats as-is (e.g. 250.0 stays 250.0).
        return rounded
    return value


def summarize_result(
    result_rows: list[dict] | None, schema: list[dict] | None = None
) -> dict | None:
    """Build a formatted summary table from aggregate result rows, or ``None``."""
    rows = result_rows or []
    if not rows:
        return None

    column_names = list(rows[0].keys())
    if not column_names:
        return None

    col_values = {c: [r.get(c) for r in rows] for c in column_names}

    columns = []
    for name in column_names:
        numeric = _column_is_numeric(col_values[name])
        columns.append(
            {
                "name": name,
                "type": "number" if numeric else "text",
                "align": "right" if numeric else "left",
            }
        )

    formatted_rows = [
        [_format_value(r.get(name)) for name in column_names] for r in rows
    ]

    return {"columns": columns, "rows": formatted_rows}
