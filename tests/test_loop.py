"""ReAct loop gate (harness/patterns/react-agent.md) — driven by FakeModel, no key.

Asserts: the loop runs a tool then finishes (≥2 iterations, tool span recorded), and a runaway model
force-finalizes at the iteration cap instead of looping forever.
"""
from langchain_core.messages import AIMessage
from sqlalchemy import select

from src.config import get_settings
from src.db import Span, get_sessionmaker
from src.runner import run_agent


def _tc(name, args, id):
    return {"name": name, "args": args, "id": id, "type": "tool_call"}


async def test_loop_runs_tool_then_finishes(FakeModelCls):
    scripted = [
        AIMessage(content="", tool_calls=[
            _tc("execute_sql", {"dataset_id": "demo", "sql": "SELECT 1"}, "a")
        ]),
        AIMessage(content="", tool_calls=[
            _tc("finish", {"answer": "Electronics leads at 3000.", "chart_spec": ""}, "b")
        ]),
    ]
    r = await run_agent("which category leads?", model=FakeModelCls(scripted))

    assert r["iterations"] >= 2
    assert r["answer"] == "Electronics leads at 3000."
    assert r["status"] == "completed"

    async with get_sessionmaker()() as s:
        spans = (await s.execute(select(Span).where(Span.run_id == r["run_id"]))).scalars().all()
    names = [sp.name for sp in spans]
    assert "execute_tool.execute_sql" in names
    assert any(sp.kind == "LLM" for sp in spans)
    assert not any("error" in (sp.attributes or {}) for sp in spans)


async def test_loop_force_finalizes_on_runaway(FakeModelCls):
    runaway = [AIMessage(content="", tool_calls=[
        _tc("execute_sql", {"dataset_id": "demo", "sql": "SELECT 1"}, "x")
    ])]
    r = await run_agent("loop forever", model=FakeModelCls(runaway))

    assert r["iterations"] == get_settings().max_iterations
    assert r["status"] == "completed"
