"""Real-LLM gates for the agentic spine — single configured provider."""
import pytest
from sqlalchemy.orm import Session

from db import session as session_module
from db.models import RunRow


@pytest.mark.usefixtures("_require_llm_key")
def test_react_loop_uses_calculator_tool(_isolated_db):
    """The loop must actually call the tool and report the right answer."""
    from graph.runner import run_agent
    run_id = run_agent("Use the calculator tool to compute 47 * 89, then state the result.")
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
    assert run.status == "completed", run.error_message
    assert "4183" in (run.output_text or "")
    # node_trace shows react was visited more than once → it looped (act+observe).
    react_visits = [t for t in (run.node_trace or []) if t["node"] == "react"]
    assert len(react_visits) >= 2


@pytest.mark.usefixtures("_require_llm_key")
def test_session_memory_remembers_across_turns(_isolated_db):
    from graph.runner import run_agent
    cid = "conv-test-1"
    run_agent("My name is Ada. Please remember my name.", conversation_id=cid)
    rid2 = run_agent("Based on our conversation, what is my name?", conversation_id=cid)
    with Session(session_module._engine) as s:
        run = s.get(RunRow, rid2)
    assert "ada" in (run.output_text or "").lower()
    # A fresh conversation does NOT know the name (isolation).
    rid3 = run_agent("Based on our conversation, what is my name?", conversation_id="conv-other")
    with Session(session_module._engine) as s:
        run3 = s.get(RunRow, rid3)
    assert "ada" not in (run3.output_text or "").lower()
