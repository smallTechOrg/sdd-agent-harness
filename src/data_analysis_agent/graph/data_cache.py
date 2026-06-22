from __future__ import annotations

import sqlite3

# Per-run in-memory SQLite connections, keyed by run_id. Connections are not
# serialisable, so they cannot live in AgentState — they live here and are
# created in load_data, read in execute_action, and cleaned up in finalize /
# handle_error.
_connections: dict[str, sqlite3.Connection] = {}


def store_connection(run_id: str, conn: sqlite3.Connection) -> None:
    """Register an in-memory connection for a run so later nodes can reuse it."""
    _connections[run_id] = conn


def get_connection(run_id: str) -> sqlite3.Connection | None:
    """Return the cached connection for a run, or ``None`` if none is registered."""
    return _connections.get(run_id)


def cleanup_connection(run_id: str) -> None:
    """Close and forget a run's connection; safe to call multiple times."""
    conn = _connections.pop(run_id, None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
