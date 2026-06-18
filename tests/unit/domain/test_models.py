from datachat.domain.models import Session, Message, Run


def test_session_model():
    s = Session(session_id="abc", filename="test.csv", status="ready", row_count=10, column_names=["a", "b"])
    assert s.session_id == "abc"
    assert s.row_count == 10
    assert s.column_names == ["a", "b"]


def test_message_model():
    m = Message(id="m1", session_id="abc", role="user", content="What is the average?")
    assert m.role == "user"
    assert m.reasoning_trace is None


def test_message_with_trace():
    trace = [{"action": "df.mean()", "result": "42.0", "is_error": False}]
    m = Message(id="m2", session_id="abc", role="assistant", content="The average is 42.", reasoning_trace=trace)
    assert len(m.reasoning_trace) == 1
    assert m.reasoning_trace[0]["action"] == "df.mean()"


def test_run_model():
    r = Run(id="r1", session_id="abc", status="completed")
    assert r.status == "completed"
    assert r.tokens_input == 0
