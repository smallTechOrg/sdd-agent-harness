"""Integration test — the real ReAct loop end-to-end (real Gemini, real DuckDB + SQLite).

Drives ≥2 iterations (a query action, then finish) and asserts loosely (structure +
non-empty), then drives the loop past max_iterations to assert force_finalize gives a
substantive best-effort answer rather than a hard failure. Skips only if the key is unset.
"""

from __future__ import annotations

import os
import uuid

import pytest

from datachat.config.settings import get_settings
from datachat.data import engine
from datachat.data.ingest import ingest_csv
from datachat.db.models import Conversation, Dataset, File
from datachat.graph.runner import run_agent

CSV = b"region,product,sales\nwest,widget,100\neast,widget,200\nwest,gadget,50\neast,gadget,75\n"

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DATA_ANALYST_GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    reason="Real Gemini key not set (DATA_ANALYST_GEMINI_API_KEY / GOOGLE_API_KEY).",
)


@pytest.mark.asyncio
async def test_real_react_loop_answers_with_table(db_session):
    dataset_id = str(uuid.uuid4())
    ds = Dataset(id=dataset_id, name="sales")
    db_session.add(ds)
    await db_session.commit()
    res = ingest_csv(dataset_id, "sales.csv", CSV)
    db_session.add(
        File(
            dataset_id=dataset_id,
            filename="sales.csv",
            duckdb_table=res.duckdb_table,
            schema_json=res.schema_columns,
            sample_rows_json=res.sample_rows,
            row_count=res.row_count,
        )
    )
    conv = Conversation(dataset_id=dataset_id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    try:
        run, assistant = await run_agent(db_session, conv, "What is the total of all sales?")
        assert run.status == "completed"
        assert run.iteration_count >= 2  # at least one action then finish
        assert assistant.role == "assistant"
        assert assistant.content.strip()
        assert run.tokens_input > 0 and run.tokens_output > 0
        # The agent actually ran a query (an action was recorded in the trace).
        assert assistant.trace_json
        assert any(not s["is_error"] for s in assistant.trace_json)
        # Loose correctness: 100+200+50+75 = 425 should appear somewhere.
        import json as _json
        haystack = assistant.content + _json.dumps(assistant.result_table_json or {})
        assert "425" in haystack
    finally:
        engine.release(dataset_id)


@pytest.mark.asyncio
async def test_force_finalize_past_max_iterations(db_session, monkeypatch):
    """A 0-iteration ceiling forces force_finalize on the first plan — substantive, not a crash."""
    monkeypatch.setattr(get_settings(), "max_iterations", 0, raising=False)

    dataset_id = str(uuid.uuid4())
    ds = Dataset(id=dataset_id, name="sales")
    db_session.add(ds)
    await db_session.commit()
    res = ingest_csv(dataset_id, "sales.csv", CSV)
    db_session.add(
        File(
            dataset_id=dataset_id,
            filename="sales.csv",
            duckdb_table=res.duckdb_table,
            schema_json=res.schema_columns,
            sample_rows_json=res.sample_rows,
            row_count=res.row_count,
        )
    )
    conv = Conversation(dataset_id=dataset_id)
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    try:
        run, assistant = await run_agent(db_session, conv, "Which region sold the most?")
        assert run.status == "completed"
        assert run.early_exit_reason == "max_iterations"
        assert assistant.content.strip()  # a best-effort answer, never empty
    finally:
        engine.release(dataset_id)
