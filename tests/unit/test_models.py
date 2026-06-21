import uuid

import duckdb
import pytest

from src.db.schema import create_tables


@pytest.fixture
def db():
    conn = duckdb.connect(":memory:")
    create_tables(conn)
    yield conn
    conn.close()


def test_datasets_table_exists(db):
    result = db.execute("SELECT COUNT(*) FROM datasets").fetchone()
    assert result[0] == 0  # empty on creation


def test_sessions_table_exists(db):
    result = db.execute("SELECT COUNT(*) FROM sessions").fetchone()
    assert result[0] == 0


def test_audit_log_table_exists(db):
    result = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()
    assert result[0] == 0


def test_messages_table_exists(db):
    result = db.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert result[0] == 0


def test_insert_dataset(db):
    db.execute(
        "INSERT INTO datasets (id, name, file_path, file_type) VALUES (?, ?, ?, ?)",
        [str(uuid.uuid4()), "sales", "/tmp/sales.csv", "csv"],
    )
    result = db.execute("SELECT name FROM datasets").fetchone()
    assert result[0] == "sales"


def test_insert_session_and_message(db):
    sid = str(uuid.uuid4())
    db.execute("INSERT INTO sessions (id) VALUES (?)", [sid])
    db.execute(
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
        [str(uuid.uuid4()), sid, "user", "hello"],
    )
    result = db.execute(
        "SELECT content FROM messages WHERE session_id = ?", [sid]
    ).fetchone()
    assert result[0] == "hello"


def test_insert_audit_log(db):
    db.execute(
        "INSERT INTO audit_log (id, query_text, rows_affected, duration_ms) VALUES (?, ?, ?, ?)",
        [str(uuid.uuid4()), "SELECT 1", 1, 5],
    )
    result = db.execute("SELECT query_text FROM audit_log").fetchone()
    assert result[0] == "SELECT 1"
