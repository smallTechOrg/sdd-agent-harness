"""run_agent — the agent entry point: build state from DB, run the graph, persist.

Loads dataset schema/sample + recent conversation turns from SQLite, ensures the dataset's
DuckDB tables are loaded, runs the ReAct graph, then writes the run + assistant message.
Provides a streaming variant that emits one `step` event per action_history append.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datachat.data import engine
from datachat.db.models import Conversation, File, Message, Run
from datachat.graph.agent import get_compiled_graph
from datachat.memory.context import summarize_schema
from datachat.observability.events import get_logger

RECENT_TURNS_LIMIT = 10


class DatasetNotLoadedError(RuntimeError):
    pass


async def _load_context(session: AsyncSession, conversation: Conversation) -> dict[str, Any]:
    files = (
        await session.execute(
            select(File).where(File.dataset_id == conversation.dataset_id)
        )
    ).scalars().all()
    if not files:
        raise DatasetNotLoadedError("This dataset has no uploaded files yet.")

    # The file-backed DuckDB persists across restarts; if its file is gone, report it.
    if not engine.has_connection(conversation.dataset_id):
        raise DatasetNotLoadedError(
            "Session data is no longer available — please re-upload the dataset's files."
        )

    file_dicts = [
        {
            "filename": f.filename,
            "duckdb_table": f.duckdb_table,
            "schema_json": f.schema_json,
            "sample_rows_json": f.sample_rows_json,
        }
        for f in files
    ]
    schema_summary, sample_rows = summarize_schema(file_dicts)

    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(RECENT_TURNS_LIMIT)
        )
    ).scalars().all()
    recent_turns = [{"role": m.role, "content": m.content} for m in reversed(rows)]
    return {
        "schema_summary": schema_summary,
        "sample_rows": sample_rows,
        "recent_turns": recent_turns,
    }


async def _run_graph(initial: dict[str, Any]) -> dict[str, Any]:
    graph = get_compiled_graph()
    return await asyncio.to_thread(graph.invoke, initial)


async def run_agent(
    session: AsyncSession, conversation: Conversation, question: str
) -> tuple[Run, Message]:
    """Run one question→answer cycle; persist the run + user/assistant messages."""
    log = get_logger(conversation_id=conversation.id)

    run = Run(conversation_id=conversation.id, status="running")
    session.add(run)
    user_msg = Message(conversation_id=conversation.id, role="user", content=question)
    session.add(user_msg)
    await session.commit()
    await session.refresh(run)

    ctx = await _load_context(session, conversation)
    initial: dict[str, Any] = {
        "run_id": run.id,
        "conversation_id": conversation.id,
        "dataset_id": conversation.dataset_id,
        "question": question,
        "action_history": [],
        "iteration_count": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        **ctx,
    }

    final = await _run_graph(initial)

    run.iteration_count = final.get("iteration_count", 0)
    run.tokens_input = final.get("tokens_input", 0)
    run.tokens_output = final.get("tokens_output", 0)
    run.estimated_cost_usd = final.get("estimated_cost_usd")
    run.early_exit_reason = final.get("early_exit_reason")
    run.completed_at = datetime.utcnow()

    if final.get("error"):
        run.status = "failed"
        run.error_message = final["error"]
        await session.commit()
        log.error("run.failed", run_id=run.id, error=final["error"])
        assistant = Message(
            conversation_id=conversation.id,
            run_id=run.id,
            role="assistant",
            content=f"Sorry — I couldn't answer this: {final['error']}",
        )
        session.add(assistant)
        await session.commit()
        await session.refresh(assistant)
        return run, assistant

    run.status = "completed"
    assistant = Message(
        conversation_id=conversation.id,
        run_id=run.id,
        role="assistant",
        content=final.get("final_answer") or "Done.",
        result_table_json=final.get("result_table"),
        chart_json=final.get("chart"),
        trace_json=final.get("action_history"),
    )
    session.add(assistant)
    await session.commit()
    await session.refresh(assistant)
    log.info("run.persisted", run_id=run.id, status=run.status)
    return run, assistant
