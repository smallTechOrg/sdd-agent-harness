import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_analysis_agent.db.models import (
    AgentRunRow,
    Base,
    McpPromptRow,
    McpResourceRow,
    DatabaseRow,
    McpToolRow,
    QueryRecordRow,
    SessionDatabaseRow,
    SessionRow,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_create_database(db):
    srv = DatabaseRow(name="sales", type="parquet", uri="parquet:///sales")
    db.add(srv)
    db.commit()
    assert srv.id is not None
    assert srv.version == 1


def test_server_name_and_uri_unique(db):
    db.add(DatabaseRow(name="a", type="parquet", uri="parquet:///a"))
    db.commit()
    db.add(DatabaseRow(name="a", type="parquet", uri="parquet:///b"))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def _tool(database_id, name, sql="SELECT 1", params=None, description="d") -> McpToolRow:
    """Build a tool row with the execution object (the canonical store)."""
    t = McpToolRow(database_id=database_id, name=name, description=description, created_version=1)
    t.execution = {"sql_template": sql, "parameters": params or []}
    return t


def test_tool_execution_accessors_and_partial_unique(db):
    srv = DatabaseRow(name="s", type="parquet", uri="parquet:///s")
    db.add(srv)
    db.flush()
    t = _tool(srv.id, "list_orders", "SELECT * FROM orders WHERE q = $q",
              [{"name": "q", "type": "string", "description": "filter"}])
    db.add(t)
    db.commit()
    db.refresh(t)
    assert t.sql_template.startswith("SELECT")                 # derived from execution
    assert t.parameters[0]["name"] == "q"
    assert t.input_schema["properties"]["q"]["type"] == "string"   # MCP inputSchema derived from params

    # A second ACTIVE tool with the same (database_id, name) violates the partial-unique index.
    db.add(_tool(srv.id, "list_orders", "SELECT 2"))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_partial_unique_allows_readd_after_soft_delete(db):
    from datetime import datetime, timezone
    srv = DatabaseRow(name="s2", type="parquet", uri="parquet:///s2")
    db.add(srv)
    db.flush()
    old = _tool(srv.id, "t", "SELECT 1", description="old")
    db.add(old)
    db.commit()
    old.deleted_at = datetime.now(timezone.utc)  # soft-delete
    db.add(_tool(srv.id, "t", "SELECT 2", description="new"))
    db.commit()  # re-add of a soft-deleted name must NOT collide
    active = db.query(McpToolRow).filter_by(database_id=srv.id, name="t", deleted_at=None).all()
    assert len(active) == 1 and active[0].description == "new"


def test_resource_uri_unique_and_size(db):
    srv = DatabaseRow(name="s_uri", type="parquet", uri="parquet:///s_uri")
    db.add(srv)
    db.flush()
    r = McpResourceRow(database_id=srv.id, uri="entity://s_uri/orders", name="orders",
                       kind="primary_entity", size=2048, created_version=1)
    db.add(r)
    db.commit()
    assert db.get(McpResourceRow, r.id).size == 2048
    # A second ACTIVE resource with the same URI violates the DB-level partial-unique index.
    db.add(McpResourceRow(database_id=srv.id, uri="entity://s_uri/orders", name="dup",
                          kind="primary_entity", created_version=1))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


def test_resource_and_prompt_rows(db):
    srv = DatabaseRow(name="s3", type="parquet", uri="parquet:///s3")
    db.add(srv)
    db.flush()
    r = McpResourceRow(database_id=srv.id, uri="dataset://s3/schema", name="schema", kind="schema")
    r.content = {"tables": {}}
    p = McpPromptRow(database_id=srv.id, name="explore")
    db.add_all([r, p])
    db.commit()
    db.refresh(r)
    assert r.content == {"tables": {}}
    assert p.arguments == []


def test_session_servers_and_query_record(db):
    srv = DatabaseRow(name="s4", type="parquet", uri="parquet:///s4")
    db.add(srv)
    db.flush()
    sess = SessionRow(name="Test session")
    db.add(sess)
    db.flush()
    db.add(SessionDatabaseRow(session_id=sess.id, database_id=srv.id))
    qr = QueryRecordRow(session_id=sess.id, question="What is the average?")
    db.add(qr)
    db.flush()
    db.add(AgentRunRow(query_record_id=qr.id))
    db.commit()
    assert qr.status == "pending"
    assert qr.query_history == []
    links = db.query(SessionDatabaseRow).filter_by(session_id=sess.id).all()
    assert len(links) == 1
