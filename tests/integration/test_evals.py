"""The eval gate as a test — `pytest -m eval`. Real LLM; all cases must pass."""
import pytest


@pytest.mark.eval
@pytest.mark.usefixtures("_require_llm_key")
def test_eval_set_all_pass(_isolated_db):
    from evals.run_evals import main
    assert main() == 0
