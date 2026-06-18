import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from datachat.db.models import Base, SessionRow, MessageRow, RunRow


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    engine.dispose()


def test_session_row_defaults(db):
    with db() as s:
        row = SessionRow(filename="data.csv")
        s.add(row)
        s.commit()
        s.refresh(row)
    assert row.id is not None
    assert row.status == "uploading"
    assert row.column_names == "[]"


def test_message_row(db):
    with db() as s:
        sess = SessionRow(filename="x.csv")
        s.add(sess)
        s.flush()
        msg = MessageRow(session_id=sess.id, role="user", content="Hello")
        s.add(msg)
        s.commit()
        s.refresh(msg)
    assert msg.id is not None
    assert msg.role == "user"


def test_run_row_defaults(db):
    with db() as s:
        sess = SessionRow(filename="x.csv")
        s.add(sess)
        s.flush()
        run = RunRow(session_id=sess.id)
        s.add(run)
        s.commit()
        s.refresh(run)
    assert run.status == "pending"
    assert run.tokens_input == 0


def test_cascade_delete(db):
    from sqlalchemy import select
    with db() as s:
        sess = SessionRow(filename="x.csv")
        s.add(sess)
        s.flush()
        msg = MessageRow(session_id=sess.id, role="user", content="Hi")
        run = RunRow(session_id=sess.id)
        s.add_all([msg, run])
        s.commit()
        sess_id = sess.id

    with db() as s:
        sess = s.get(SessionRow, sess_id)
        s.delete(sess)
        s.commit()
        remaining_msgs = s.execute(select(MessageRow).where(MessageRow.session_id == sess_id)).scalars().all()
        remaining_runs = s.execute(select(RunRow).where(RunRow.session_id == sess_id)).scalars().all()

    assert remaining_msgs == []
    assert remaining_runs == []
