"""Migration test for the fresh single initial schema (835cdb8ae996): upgrade from empty builds the
whole MCP-server schema, the partial-unique index over active capability rows is enforced, and
downgrade to base drops everything (round-trip)."""
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_REPO = Path(__file__).resolve().parents[3]
_TABLES = {
    "databases", "mcp_tools", "mcp_resources", "mcp_prompts",
    "sessions", "session_databases", "query_records", "agent_runs",
}


def _cfg() -> Config:
    cfg = Config(str(_REPO / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO / "alembic"))
    return cfg


@pytest.fixture
def cfg_db(tmp_path, monkeypatch):
    db_path = tmp_path / "mig.db"
    monkeypatch.setenv("DATAANALYSIS_DATABASE_URL", f"sqlite:///{db_path}")
    return _cfg(), db_path


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_upgrade_creates_schema(cfg_db):
    cfg, db_path = cfg_db
    command.upgrade(cfg, "head")
    assert _TABLES <= _table_names(db_path)


def test_partial_unique_index_enforced(cfg_db):
    cfg, db_path = cfg_db
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO databases (id,name,type,uri,version,created_at) "
        "VALUES ('s','s','parquet','parquet:///s',1,'2026-01-01 00:00:00')"
    )
    conn.execute(
        "INSERT INTO mcp_tools (id,database_id,name,description,execution_json,"
        "created_version,created_at,updated_at) "
        "VALUES ('t1','s','dup','d','{}',1,'2026-01-01 00:00:00','2026-01-01 00:00:00')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO mcp_tools (id,database_id,name,description,execution_json,"
            "created_version,created_at,updated_at) "
            "VALUES ('t2','s','dup','d','{}',1,'2026-01-01 00:00:00','2026-01-01 00:00:00')"
        )
        conn.commit()
    conn.close()


def test_downgrade_reverses(cfg_db):
    cfg, db_path = cfg_db
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    assert not (_TABLES & _table_names(db_path))
