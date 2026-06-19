"""Demo-gate eval, in-process (harness/patterns/observability-and-evals.md).

A REAL run on the seeded dataset, then BOTH evals — a 200 with a wrong answer fails here. Needs a funded
APP_LLM_API_KEY (loaded from .env); skipped offline. The end-to-end HTTP version is harness/scripts/demo_gate.sh.
"""
import pytest

from agent.config import get_settings
from agent.evals import outcome_eval, trajectory_eval
from agent.gate_eval import CRITERION, EVALUATION_STEPS, EXPECT_TOOLS, FORBID_TOOLS
from agent.runner import run_agent
from agent.seed import seed

pytestmark = pytest.mark.skipif(
    not get_settings().llm_api_key, reason="no funded APP_LLM_API_KEY (real-run gate)")

GOAL = "Which product category has the highest total sales, and what is that total?"


async def test_demo_gate_real_run():
    dataset_id = await seed()
    r = await run_agent(GOAL, dataset_id=dataset_id)
    assert r["status"] == "completed", r

    ok_t, reasons = await trajectory_eval(r["run_id"], expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)
    assert ok_t, f"TRAJECTORY failed: {reasons}"

    ok_o, score, text = await outcome_eval(GOAL, r["answer"], CRITERION, EVALUATION_STEPS)
    assert ok_o, f"OUTCOME failed: score {score}\n{text}\nanswer={r['answer']!r}"
    # the ground truth: Electronics totals 3000 in the seeded data
    assert "electronic" in (r["answer"] or "").lower()
