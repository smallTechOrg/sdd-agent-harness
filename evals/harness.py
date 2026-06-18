"""Eval harness — run each case through the agent, score loosely, persist eval_results.

Real model. A case passes if the answer (or its result table) contains the expected
value — a property check, not an exact-text match.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from datachat.data import engine
from datachat.data.ingest import ingest_csv
from datachat.db.models import Conversation, Dataset, EvalResult, File
from datachat.graph.runner import run_agent
from evals.dataset import EVAL_CASES, EVAL_CSV


def _hit(answer: str, table: dict | None, case: dict) -> bool:
    haystack = (answer or "") + json.dumps(table or {})
    if "expect_substring" in case:
        return case["expect_substring"] in haystack
    if "expect_substring_any" in case:
        return any(s in haystack for s in case["expect_substring_any"])
    return bool(answer)


async def run_evals(session: AsyncSession) -> list[EvalResult]:
    dataset_id = str(uuid.uuid4())
    ds = Dataset(id=dataset_id, name="eval-fixture")
    session.add(ds)
    await session.commit()
    res = ingest_csv(dataset_id, "eval.csv", EVAL_CSV)
    session.add(
        File(
            dataset_id=dataset_id,
            filename="eval.csv",
            duckdb_table=res.duckdb_table,
            schema_json=res.schema_columns,
            sample_rows_json=res.sample_rows,
            row_count=res.row_count,
        )
    )
    await session.commit()

    results: list[EvalResult] = []
    try:
        for case in EVAL_CASES:
            conv = Conversation(dataset_id=dataset_id)
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            _run, assistant = await run_agent(session, conv, case["question"])
            passed = _hit(assistant.content, assistant.result_table_json, case)
            res = EvalResult(
                case_name=case["name"],
                passed=passed,
                detail=assistant.content[:500],
            )
            session.add(res)
            await session.commit()
            results.append(res)
    finally:
        engine.release(dataset_id)
    return results


if __name__ == "__main__":  # manual run: uv run python -m evals.harness
    from datachat.db.session import get_sessionmaker, init_db

    async def _main():
        await init_db()
        async with get_sessionmaker()() as s:
            for r in await run_evals(s):
                print(f"{'PASS' if r.passed else 'FAIL'}  {r.case_name}: {r.detail[:80]}")

    asyncio.run(_main())
