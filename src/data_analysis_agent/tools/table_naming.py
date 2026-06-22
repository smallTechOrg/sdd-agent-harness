from __future__ import annotations

import re


def sql_table_name(source_name: str) -> str:
    """Derive a SQL-safe table name from a data source name or filename.

    Lowercases the filename stem, replaces every non-word character with an
    underscore, collapses repeats, and prefixes ``ds_`` if the result would
    otherwise start with a digit. Falls back to ``data`` for empty input.

    Args:
        source_name: The data source display name, e.g. ``"2024 Sales.csv"``.

    Returns:
        A lowercase identifier safe to use as a SQL table name, e.g. ``ds_2024_sales``.
    """
    stem = source_name.rsplit(".", 1)[0]
    name = re.sub(r"[^\w]", "_", stem).lower()
    name = re.sub(r"_+", "_", name).strip("_") or "data"
    if name[0].isdigit():
        name = "ds_" + name
    return name
