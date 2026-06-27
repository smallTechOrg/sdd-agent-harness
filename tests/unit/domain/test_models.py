from data_analysis_agent.domain.models import Database, Session, QueryRecord, AgentRunRecord


def test_database_defaults():
    s = Database(name="sales")
    assert s.id is not None
    assert s.type == "parquet"
    assert s.version == 1


def test_session_defaults():
    s = Session(database_ids=["s1", "s2"])
    assert s.id is not None
    assert s.name is None
    assert s.database_ids == ["s1", "s2"]


def test_query_record_defaults():
    qr = QueryRecord(session_id="s1", question="What is the total?")
    assert qr.id is not None
    assert qr.status == "pending"
    assert qr.answer is None


def test_agent_run_record_defaults():
    run = AgentRunRecord(query_record_id="xyz")
    assert run.id is not None
    assert run.status == "pending"
