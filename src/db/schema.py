import duckdb

CREATE_DATASETS = """
CREATE TABLE IF NOT EXISTS datasets (
    id          VARCHAR PRIMARY KEY,
    name        VARCHAR NOT NULL UNIQUE,
    file_path   VARCHAR NOT NULL,
    file_type   VARCHAR NOT NULL,
    row_count   INTEGER,
    column_names VARCHAR[],
    created_at  TIMESTAMP DEFAULT NOW()
)
"""

CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
)
"""

CREATE_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id           VARCHAR PRIMARY KEY,
    session_id   VARCHAR,
    query_text   VARCHAR NOT NULL,
    rows_affected INTEGER,
    duration_ms  INTEGER,
    created_at   TIMESTAMP DEFAULT NOW()
)
"""

CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id          VARCHAR PRIMARY KEY,
    session_id  VARCHAR NOT NULL REFERENCES sessions(id),
    role        VARCHAR NOT NULL,
    content     VARCHAR NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW()
)
"""


def create_tables(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(CREATE_DATASETS)
    conn.execute(CREATE_SESSIONS)
    conn.execute(CREATE_AUDIT_LOG)
    conn.execute(CREATE_MESSAGES)
