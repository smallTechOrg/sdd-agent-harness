"""DB layer tests — no LLM key required."""
import json
from sqlalchemy.orm import Session
from db.models import UploadSession, QueryRun


def test_upload_session_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        session = UploadSession(
            table_name="test_table_abc12345",
            original_filename="test.csv",
            row_count=10,
            col_count=3,
            schema_json=json.dumps([{"column": "id", "type": "INTEGER"}]),
        )
        s.add(session)
        s.commit()
        session_id = session.id

    with Session(_isolated_db) as s:
        fetched = s.get(UploadSession, session_id)
        assert fetched is not None
        assert fetched.original_filename == "test.csv"
        assert fetched.row_count == 10
        assert fetched.col_count == 3
        schema = json.loads(fetched.schema_json)
        assert schema[0]["column"] == "id"


def test_query_run_roundtrip(_isolated_db):
    with Session(_isolated_db) as s:
        upload = UploadSession(
            table_name="sales_abc12345",
            original_filename="sales.csv",
            row_count=5,
            col_count=2,
            schema_json="[]",
        )
        s.add(upload)
        s.commit()
        session_id = upload.id

    with Session(_isolated_db) as s:
        run = QueryRun(
            session_id=session_id,
            question="What are total sales?",
            status="pending",
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(QueryRun, run_id)
        assert run is not None
        assert run.question == "What are total sales?"
        assert run.status == "pending"
        assert run.sql is None


def test_query_run_status_update(_isolated_db):
    with Session(_isolated_db) as s:
        upload = UploadSession(
            table_name="data_ab123456",
            original_filename="data.csv",
            row_count=3,
            col_count=1,
            schema_json="[]",
        )
        s.add(upload)
        s.commit()
        session_id = upload.id

    with Session(_isolated_db) as s:
        run = QueryRun(
            session_id=session_id,
            question="Test?",
            status="pending",
        )
        s.add(run)
        s.commit()
        run_id = run.id

    with Session(_isolated_db) as s:
        run = s.get(QueryRun, run_id)
        run.status = "completed"
        run.sql = "SELECT * FROM data_ab123456"
        run.insight = "Some insight."
        s.commit()

    with Session(_isolated_db) as s:
        run = s.get(QueryRun, run_id)
        assert run.status == "completed"
        assert run.sql == "SELECT * FROM data_ab123456"
        assert run.insight == "Some insight."
