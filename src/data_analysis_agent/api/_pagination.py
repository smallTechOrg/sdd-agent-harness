"""Offset-window pagination for the server-rendered UI lists.

The UI renders the first page inline (``index.html``) and fetches subsequent pages as HTML fragments
(``api/fragments.py``) appended client-side via a "Load more" button. Offset windows are used (rather
than the JSON-RPC keyset cursors) because the UI lists order by mutable fields (e.g. a session's
``updated_at``); for an admin-scale UI the small offset-shift risk on concurrent inserts is acceptable.
"""
from __future__ import annotations


def page_window(query, *, offset: int, limit: int) -> tuple[list, bool]:
    """Return ``(rows, has_more)`` for one offset window of ``query``.

    Fetches ``limit + 1`` rows so ``has_more`` is known without a separate COUNT, then trims to ``limit``.
    """
    rows = query.offset(max(offset, 0)).limit(limit + 1).all()
    has_more = len(rows) > limit
    return rows[:limit], has_more
