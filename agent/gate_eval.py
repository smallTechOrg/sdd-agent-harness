"""The eval half of the demo gate (harness/workflows/gates.md).

Exit 0 iff the run's answer is right (OUTCOME ≥ threshold) AND the path is sane (TRAJECTORY).
Criterion + steps + expect_tools fed from spec/capabilities/nl-query.md.
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from .db import Run, get_sessionmaker
from .evals import outcome_eval, trajectory_eval

CRITERION = (
    "WHEN the user asks a question answerable from the dataset the system SHALL ground its answer "
    "in the result of a read-only SQL query it executed via execute_sql (no invented figures)."
)
EVALUATION_STEPS = [
    "Does the answer identify the category with the highest total sales "
    "(the dataset's answer is Electronics) and state its total (3000)?",
    "Is the figure grounded — consistent with what a read-only SQL aggregation over the dataset "
    "would produce — rather than invented or hallucinated?",
    "A brief additional insight or interpretation is acceptable and expected; do NOT lower the "
    "score for one as long as it is consistent with the data.",
]
EXPECT_TOOLS = ["execute_sql"]
FORBID_TOOLS = []


async def main(run_id: str, goal: str) -> int:
    async with get_sessionmaker()() as s:
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
    ok_o, score, text = await outcome_eval(goal, run.answer, CRITERION, EVALUATION_STEPS)
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=EXPECT_TOOLS, forbid_tools=FORBID_TOOLS)
    if not ok_o:
        print(f"OUTCOME FAIL: score {score} < threshold\n--- judge ---\n{text}", file=sys.stderr)
    if not ok_t:
        print(f"TRAJECTORY FAIL: {reasons}", file=sys.stderr)
    if ok_o and ok_t:
        print(f"EVAL PASS: outcome score {score}, trajectory clean")
    return 0 if (ok_o and ok_t) else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--goal", required=True)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.run_id, a.goal)))
