"""run_agent — drive one run end-to-end (harness/patterns/interface.md).

Create the Run, resolve the active dataset (set into the tools' ContextVar), seed the domain prompt + goal,
invoke the graph under the invoke_agent span, persist messages + outcome. run_id is returned so the caller
can deep-link into /traces.
"""
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select

from .config import get_settings
from .db import Message, Run, get_sessionmaker
from .domain import Dataset
from .graph import build_graph, content_to_text
from .llm import get_model
from .observability import span
from .tools import current_dataset

DOMAIN_PROMPT = (
    "You are DataChat, a careful, precise data analyst working over the user's uploaded dataset.\n\n"
    "Ground every answer in the data:\n"
    "- First call get_schema to see the available tables, columns, and types.\n"
    "- Then call run_sql with a single READ-ONLY SELECT to compute the answer. Every figure you state must "
    "come from a query result you ran this turn — never invent or estimate numbers.\n\n"
    "SQL rules:\n"
    "- Read-only only (SELECT / WITH). INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/COPY/ATTACH/PRAGMA are refused.\n"
    "- Use the exact table and column names from get_schema (quote identifiers containing spaces). Aggregate "
    "when the user wants a number; add LIMIT when returning rows.\n\n"
    "If the question cannot be answered from the available tables/columns, say so plainly and name what data "
    "would be needed — do not guess.\n\n"
    "After the direct answer, add one short, factual insight when the data shows something notable (a leader, "
    "an outlier, a trend), grounded in what you queried.\n\n"
    "Be concise and numeric. Lead with the answer. Call finish exactly once with the final answer."
)


async def _resolve_dataset_id(dataset_id: str | None) -> str | None:
    if dataset_id:
        return dataset_id
    async with get_sessionmaker()() as s:               # demo convenience: default to the latest dataset
        row = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().first()
        return row.id if row else None


async def run_agent(goal: str, dataset_id: str | None = None, model=None, run_id: str | None = None) -> dict:
    settings = get_settings()  # noqa: F841 — kept for parity/escalation; loop reads settings in graph
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()
    dataset_id = await _resolve_dataset_id(dataset_id)

    token = current_dataset.set(dataset_id)
    try:
        async with get_sessionmaker()() as s:
            s.add(Run(id=run_id, goal=goal, status="running", iterations=0))
            await s.commit()

        graph = build_graph(model)
        state = {
            "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content=goal)],
            "iterations": 0, "answer": None, "run_id": run_id,
        }
        try:
            async with span(run_id, "invoke_agent", "INTERNAL", goal=goal, dataset_id=dataset_id):
                result = await graph.ainvoke(state, config={"recursion_limit": 50})
        except Exception as e:
            async with get_sessionmaker()() as s:
                run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
                run.status, run.answer = "error", f"error: {e}"
                await s.commit()
            raise

        async with get_sessionmaker()() as s:
            for m in result["messages"]:
                role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
                s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role,
                              content=content_to_text(m.content)))
            run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
            run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]
            await s.commit()

        return {"run_id": run_id, "answer": result["answer"], "iterations": result["iterations"],
                "dataset_id": dataset_id, "status": "completed", "messages": result["messages"]}
    finally:
        current_dataset.reset(token)
