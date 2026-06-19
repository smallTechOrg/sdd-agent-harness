"""run_agent — drive one run end-to-end (harness/patterns/interface.md).

Accepts optional thread_id for multi-turn conversation (AsyncSqliteSaver checkpointer keyed to thread_id).
Accepts optional graph so the server can pass the compiled graph with the persistent checkpointer.
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

DOMAIN_PROMPT = (
    "You are DataChat, a precise and helpful data-analysis assistant. You help users understand their "
    "uploaded datasets by translating natural-language questions into SQL queries and presenting results clearly.\n\n"
    "Rules you must always follow:\n\n"
    "1. Only query data that has been uploaded in this session. Never invent, assume, or hallucinate data "
    "values, column names, or table names. If you are unsure whether a column exists, call "
    "get_dataset_schema first.\n"
    "2. Only use SELECT statements with execute_sql. Never generate or run INSERT, UPDATE, DELETE, DROP, "
    "CREATE, or any other mutating SQL. If asked to modify or delete data, explain that you are a "
    "read-only analysis tool.\n"
    "3. Before writing a SQL query, call list_datasets (if you do not already know which datasets are "
    "loaded) and get_dataset_schema (to confirm column names and types). Never guess a column name.\n"
    "4. When the user's question is naturally answered with a chart, call generate_chart_spec after "
    "execute_sql to produce a Plotly JSON spec. Pass the chart_spec to finish alongside the prose answer.\n"
    "5. In multi-turn conversations, use the prior messages to understand what the user is refining or "
    "following up on. Do not ask the user to repeat context that is already in the conversation.\n"
    "6. Be concise and direct. Lead with the answer, then explain the SQL or methodology only if asked.\n"
    "7. If a question is out of scope (e.g. write code, access external URLs, or perform actions outside "
    "data analysis), decline politely and redirect to what you can do.\n"
    "8. Call finish exactly once, after you have the complete answer (prose + optional chart_spec). "
    "Do not call finish before you have queried the data.\n"
)


async def _resolve_dataset_id(dataset_id: str | None) -> str | None:
    if dataset_id:
        return dataset_id
    async with get_sessionmaker()() as s:
        row = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().first()
        return row.id if row else None


async def run_agent(
    goal: str,
    dataset_id: str | None = None,
    thread_id: str | None = None,
    model=None,
    run_id: str | None = None,
    graph=None,
) -> dict:
    settings = get_settings()  # noqa: F841
    run_id = run_id or uuid.uuid4().hex
    thread_id = thread_id or uuid.uuid4().hex
    model = model or get_model()
    dataset_id = await _resolve_dataset_id(dataset_id)

    async with get_sessionmaker()() as s:
        s.add(Run(id=run_id, goal=goal, status="running", iterations=0))
        await s.commit()

    if graph is None:
        graph = build_graph(model)

    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content=goal)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }
    invoke_cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    try:
        async with span(run_id, "invoke_agent", "INTERNAL", goal=goal, dataset_id=dataset_id,
                        thread_id=thread_id):
            result = await graph.ainvoke(state, config=invoke_cfg)
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

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "answer": result["answer"],
        "iterations": result["iterations"],
        "dataset_id": dataset_id,
        "status": "completed",
        "messages": result["messages"],
    }
