"""The eval half of the demo gate (harness/workflows/gates.md).

Exit 0 iff the run's answer is right (OUTCOME ≥ threshold) AND the path is sane (TRAJECTORY). The criterion
+ steps + expect_tools come from spec/capabilities/query-data.md (the demo-gate capability).
"""
import argparse
import asyncio
import sys

from sqlalchemy import select

from .db import Run, get_sessionmaker
from .evals import outcome_eval, trajectory_eval

# Filled from spec/capabilities/query-data.md (the demo-gate capability's EARS line + eval handles).
CRITERION = ("WHEN the user asks a question answerable from the dataset the system SHALL ground its answer "
             "in the result of a read-only SQL query it executed over the dataset's tables (no invented figures).")
EVALUATION_STEPS = [
    "Does the answer identify the category with the highest total sales (the dataset's answer is Electronics) "
    "and state its total (3000)?",
    "Is the figure grounded — the kind of value a read-only SQL aggregation over the dataset would produce — "
    "rather than invented or contradicted by the data?",
    "A brief additional insight or interpretation is acceptable and even expected (see the product's domain "
    "instructions); do NOT lower the score for including one as long as it is consistent with the data.",
]
EXPECT_TOOLS = ["run_sql"]
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
