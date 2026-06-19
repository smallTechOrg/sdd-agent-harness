"""run_agent — drive one run end-to-end (harness/patterns/interface.md).

Create the Run, resolve the active dataset (set into the tools' ContextVar), reconstruct prior conversation
turns into the window for follow-ups, seed the domain prompt + goal, invoke the graph under the
invoke_agent span, persist messages + any charts + outcome, and link the run into its conversation.
"""
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import func, select

from .config import get_settings
from .db import Message, Run, get_sessionmaker
from .domain import Chart, Conversation, ConversationTurn, Dataset
from .graph import build_graph, content_to_text
from .llm import get_model
from .observability import span
from .tools import current_dataset, run_charts

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
    "Charts: when a trend, comparison, or distribution is clearer as a picture — or the user asks for a "
    "chart — call create_chart with a read-only SQL query and a Vega-Lite v5 spec (a `mark` plus an "
    "`encoding` whose field names match the query's result columns). Use line for trends over time, bar for "
    "category comparisons, point for relationships.\n\n"
    "Conversation: treat follow-up questions as continuing the same analysis — reuse the dataset and prior "
    "results, and resolve references ('those', 'that region', 'by month instead') against the previous "
    "turns shown above. If a follow-up is genuinely ambiguous, ask one brief clarifying question.\n\n"
    "If the question cannot be answered from the available tables/columns, say so plainly and name what data "
    "would be needed — do not guess.\n\n"
    "After the direct answer, add one short, factual insight when the data shows something notable. Be "
    "concise and numeric. Lead with the answer. Call finish exactly once with the final answer."
)


async def _resolve_dataset_id(dataset_id: str | None, conversation_id: str | None) -> str | None:
    if dataset_id:
        return dataset_id
    if conversation_id:
        async with get_sessionmaker()() as s:
            conv = await s.get(Conversation, conversation_id)
            if conv and conv.dataset_id:
                return conv.dataset_id
    async with get_sessionmaker()() as s:               # demo convenience: default to the latest dataset
        row = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().first()
        return row.id if row else None


async def _load_history(conversation_id: str, limit: int = 8) -> list[tuple[str, str]]:
    """Prior (goal, answer) pairs for this conversation, oldest→newest, capped to the last `limit`."""
    async with get_sessionmaker()() as s:
        rows = (await s.execute(
            select(Run.goal, Run.answer)
            .join(ConversationTurn, ConversationTurn.run_id == Run.id)
            .where(ConversationTurn.conversation_id == conversation_id)
            .order_by(ConversationTurn.idx))).all()
    pairs = [(g, a) for g, a in rows if a]
    return pairs[-limit:]


async def run_agent(goal: str, dataset_id: str | None = None, model=None,
                    run_id: str | None = None, conversation_id: str | None = None) -> dict:
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()
    dataset_id = await _resolve_dataset_id(dataset_id, conversation_id)
    history = await _load_history(conversation_id) if conversation_id else []

    token_ds = current_dataset.set(dataset_id)
    token_ch = run_charts.set([])
    try:
        async with get_sessionmaker()() as s:
            s.add(Run(id=run_id, goal=goal, status="running", iterations=0))
            await s.commit()

        graph = build_graph(model)
        messages = [SystemMessage(content=DOMAIN_PROMPT)]
        for h_goal, h_answer in history:                 # reconstruct prior turns for follow-ups
            messages.append(HumanMessage(content=h_goal))
            messages.append(AIMessage(content=h_answer))
        messages.append(HumanMessage(content=goal))
        state = {"messages": messages, "iterations": 0, "answer": None, "run_id": run_id}

        try:
            async with span(run_id, "invoke_agent", "INTERNAL", goal=goal, dataset_id=dataset_id,
                            conversation_id=conversation_id, prior_turns=len(history)):
                result = await graph.ainvoke(state, config={"recursion_limit": 50})
        except Exception as e:
            async with get_sessionmaker()() as s:
                run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
                run.status, run.answer = "error", f"error: {e}"
                await s.commit()
            raise

        charts = run_charts.get() or []
        async with get_sessionmaker()() as s:
            for m in result["messages"]:
                role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
                s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role,
                              content=content_to_text(m.content)))
            for c in charts:
                s.add(Chart(run_id=run_id, title=c.get("title", ""), spec=c["spec"]))
            run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
            run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]
            if conversation_id:
                idx = (await s.execute(select(func.count()).select_from(ConversationTurn)
                       .where(ConversationTurn.conversation_id == conversation_id))).scalar_one()
                s.add(ConversationTurn(conversation_id=conversation_id, run_id=run_id, idx=idx))
            await s.commit()

        return {"run_id": run_id, "answer": result["answer"], "iterations": result["iterations"],
                "dataset_id": dataset_id, "conversation_id": conversation_id, "status": "completed",
                "charts": charts, "messages": result["messages"]}
    finally:
        current_dataset.reset(token_ds)
        run_charts.reset(token_ch)
