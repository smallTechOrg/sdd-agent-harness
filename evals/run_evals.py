"""No-eval-no-launch gate. Runs the assembled agent over cases.jsonl and scores
each answer with an LLM-as-judge (pass/fail vs the case's `expect`). Green = all
cases pass. Run: `make eval` or `pytest -m eval`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from graph.runner import run_agent          # noqa: E402
from llm.client import LLMClient            # noqa: E402
from db.session import create_db_session, init_db  # noqa: E402
from db.models import RunRow                # noqa: E402

CASES = Path(__file__).parent / "cases.jsonl"
JUDGE = (
    "You are a strict grader. Given a user request, the expected criterion, and "
    "the agent's answer, reply with exactly PASS or FAIL.\n\n"
    "Request: {input}\nExpected: {expect}\nAnswer: {answer}\n\nVerdict:"
)


def _judge(case: dict, answer: str) -> bool:
    resp = LLMClient().call_model(JUDGE.format(answer=answer, **case))
    return "PASS" in resp.text.upper()


def main() -> int:
    init_db()
    cases = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    passed = 0
    for c in cases:
        rid = run_agent(c["input"])
        with create_db_session() as s:
            answer = s.get(RunRow, rid).output_text or ""
        ok = _judge(c, answer)
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {c['input'][:50]}")
    print(f"\n{passed}/{len(cases)} passed")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
