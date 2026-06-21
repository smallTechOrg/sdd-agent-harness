"""run_agent — drive one run end-to-end (harness/patterns/interface.md).

Accepts optional thread_id for multi-turn conversation (AsyncSqliteSaver checkpointer keyed to thread_id).
Accepts optional graph so the server can pass the compiled graph with the persistent checkpointer.
"""
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select

from .config import get_settings
from .db import Message, Run, Span, get_sessionmaker
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


async def _sum_llm_tokens(run_id: str) -> tuple[int, int]:
    """Sum input/output tokens from all LLM spans for this run."""
    from sqlalchemy import select
    async with get_sessionmaker()() as s:
        spans = (await s.execute(
            select(Span).where(Span.run_id == run_id, Span.kind == "LLM")
        )).scalars().all()
    inp = sum((sp.attributes or {}).get("tokens", {}).get("input_tokens", 0) for sp in spans)
    out = sum((sp.attributes or {}).get("tokens", {}).get("output_tokens", 0) for sp in spans)
    return inp, out


def _calc_cost(inp: int, out: int) -> float:
    s = get_settings()
    return round(inp * s.llm_input_cost_per_1m / 1_000_000 + out * s.llm_output_cost_per_1m / 1_000_000, 6)


async def _upsert_thread(thread_id: str, dataset_id: str | None, title: str,
                          inp: int, out: int, cost: float) -> None:
    from .domain import Thread
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    async with get_sessionmaker()() as s:
        thread = await s.get(Thread, thread_id)
        if thread is None:
            s.add(Thread(
                id=thread_id, dataset_id=dataset_id,
                title=title[:120],
                total_input_tokens=inp, total_output_tokens=out, total_cost_usd=cost,
                run_count=1,
            ))
        else:
            thread.total_input_tokens += inp
            thread.total_output_tokens += out
            thread.total_cost_usd = round(thread.total_cost_usd + cost, 6)
            thread.run_count += 1
            thread.last_active_at = now
        await s.commit()


async def _dataset_context(dataset_id: str | None) -> str:
    """Return a system-message suffix describing the active dataset schema."""
    if not dataset_id:
        return ""
    from . import duck
    from .domain import Dataset
    from sqlalchemy import select
    try:
        async with get_sessionmaker()() as s:
            ds = await s.get(Dataset, dataset_id)
        if not ds:
            return ""
        schema = await __import__("asyncio").to_thread(duck.dataset_schema, dataset_id)
        lines = [f"\nACTIVE DATASET: {ds.name!r} (id={dataset_id})"]
        lines.append("You have exclusive access to this dataset. Do NOT call list_datasets — use this dataset_id directly.")
        lines.append("Schema:")
        for t in schema.get("tables", []):
            cols = ", ".join(f"{c['name']} ({c['type']})" for c in t["columns"])
            lines.append(f"  TABLE {t['table']!r}: {cols}")
            if t.get("sample_rows"):
                names = [c["name"] for c in t["columns"]]
                sample = "; ".join(str(dict(zip(names, r))) for r in t["sample_rows"][:2])
                lines.append(f"    sample: {sample}")
        return "\n".join(lines)
    except Exception:
        return ""


async def _resolve_dataset_id(dataset_id: str | None) -> str | None:
    if dataset_id:
        return dataset_id
    async with get_sessionmaker()() as s:
        row = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().first()
        return row.id if row else None


async def _load_prior_messages(graph, thread_id: str) -> list:
    """Load prior messages from the thread's checkpoint for multi-turn context."""
    cp_obj = getattr(graph, "checkpointer", None)
    if cp_obj is None:
        return []
    try:
        cp = await cp_obj.aget({"configurable": {"thread_id": thread_id}})
        if cp is None:
            return []
        # Checkpoint may be a Checkpoint namedtuple or a raw dict depending on LangGraph version
        cv = cp.get("channel_values") if isinstance(cp, dict) else getattr(cp, "channel_values", None)
        if cv:
            return list(cv.get("messages", []))
    except Exception:
        pass
    return []


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

    ds_context = await _dataset_context(dataset_id)
    system_content = DOMAIN_PROMPT + ds_context

    prior_messages = await _load_prior_messages(graph, thread_id)
    if prior_messages:
        # Always refresh the system message so the current dataset context is applied.
        non_sys = [m for m in prior_messages if not isinstance(m, SystemMessage)]
        new_messages = [SystemMessage(content=system_content)] + non_sys + [HumanMessage(content=goal)]
    else:
        new_messages = [SystemMessage(content=system_content), HumanMessage(content=goal)]

    state = {
        "messages": new_messages,
        "iterations": 0, "answer": None, "chart_spec": None, "run_id": run_id,
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

    inp, out = await _sum_llm_tokens(run_id)
    cost = _calc_cost(inp, out)

    async with get_sessionmaker()() as s:
        for m in result["messages"]:
            role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
            s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role,
                          content=content_to_text(m.content)))
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]
        run.thread_id = thread_id
        run.input_tokens, run.output_tokens, run.cost_usd = inp, out, cost
        await s.commit()

    await _upsert_thread(thread_id, dataset_id, goal, inp, out, cost)

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "answer": result["answer"],
        "chart_spec": result.get("chart_spec"),
        "iterations": result["iterations"],
        "dataset_id": dataset_id,
        "status": "completed",
        "input_tokens": inp,
        "output_tokens": out,
        "cost_usd": cost,
        "messages": result["messages"],
    }
