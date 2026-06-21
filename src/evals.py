"""Evals — OUTCOME (LLM-judge) + TRAJECTORY (deterministic span read).

Fed by the EARS criteria in spec/capabilities/*.md. A 200 with a wrong answer fails the OUTCOME half.
harness/patterns/observability-and-evals.md.
"""
import re

from sqlalchemy import select

from .db import Span, get_sessionmaker
from .llm import get_model

JUDGE_PROMPT = """You are a strict grader. Score 0-5 how well the ANSWER satisfies the CRITERION.
Work through each evaluation step, then output the final integer score on the last line as `SCORE: <n>`.

CRITERION (EARS): {criterion}
EVALUATION STEPS:
{steps}

GOAL: {goal}
ANSWER: {answer}"""


def _parse_score(text: str) -> int:
    for ln in reversed(text.splitlines()):
        if ln.upper().strip().startswith("SCORE:"):
            m = re.search(r"\d+", ln)
            if m:
                return int(m.group())
    nums = re.findall(r"\b[0-5]\b", text)
    return int(nums[-1]) if nums else 0


async def outcome_eval(goal, answer, criterion, evaluation_steps, *, threshold=4):
    """OUTCOME: LLM-judge the answer against one EARS criterion. Returns (passed, score, text)."""
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(evaluation_steps))
    msg = JUDGE_PROMPT.format(criterion=criterion, steps=steps, goal=goal, answer=answer)
    resp = await get_model().ainvoke(msg)             # judge model — cheap tier by default
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    score = _parse_score(text)
    return score >= threshold, score, text


async def trajectory_eval(run_id, *, expect_tools, forbid_tools=()):
    """TRAJECTORY: deterministic read of the spans table — no LLM. Returns (passed, reasons).

    Note: unlike the generic recipe, this build does NOT fail on duplicate tool calls — a data-analysis
    agent legitimately issues several read-only queries in one run. expect/forbid + the error-span check are
    the assertions that matter here.
    """
    async with get_sessionmaker()() as s:
        spans = (await s.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.start_ms))).scalars().all()
    tool_calls = [sp.name.removeprefix("execute_tool.") for sp in spans if sp.kind == "TOOL"]
    reasons = []
    for t in expect_tools:
        if t not in tool_calls:
            reasons.append(f"missing expected tool: {t}")
    for t in forbid_tools:
        if t in tool_calls:
            reasons.append(f"forbidden/ungated tool fired: {t}")
    if any("error" in (sp.attributes or {}) for sp in spans):
        reasons.append("a span recorded an error")
    return not reasons, reasons
