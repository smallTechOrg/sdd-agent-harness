import pytest
from sqlalchemy.orm import Session

from agent.graph.runner import run_agent
from agent.db import session as session_module
from agent.db.models import RunRow


@pytest.mark.usefixtures("_require_api_key")
def test_pipeline_runs_end_to_end(_isolated_db):
    run_id = run_agent("Explain why the sky is blue in simple terms.")
    assert run_id is not None
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
        assert run is not None
        assert run.status == "completed"
        assert run.output_text and len(run.output_text) > 10


@pytest.mark.usefixtures("_require_api_key")
def test_pipeline_stores_input(_isolated_db):
    input_text = "The quick brown fox."
    run_id = run_agent(input_text)
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
        assert run.input_text == input_text
