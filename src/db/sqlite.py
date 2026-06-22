import aiosqlite
from src.config import get_settings


async def get_db_path() -> str:
    return get_settings().sqlite_path


async def create_tables_sqlite() -> None:
    db_path = get_settings().sqlite_path
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""CREATE TABLE IF NOT EXISTS session (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS dataset (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            file_format TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            column_names TEXT NOT NULL DEFAULT '[]',
            duckdb_table TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS query_run (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            sql TEXT,
            row_count INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            completed_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS conversation_message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES session(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            session_id TEXT,
            action TEXT NOT NULL,
            payload TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            duration_ms INTEGER,
            created_at TEXT NOT NULL
        )""")
        # Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_dataset_session ON dataset(session_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_qrun_session ON query_run(session_id)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_msg_session ON conversation_message(session_id, created_at)"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log(run_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id)")
        await db.commit()
