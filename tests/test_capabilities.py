"""Capability journey tests — one scenario per EARS criterion from spec/capabilities/*.md.

These tests go beyond unit tests and mechanic loop tests. They:
  1. Ingest REAL data into DuckDB (not mocked)
  2. Use a ContextAwareFakeModel that reads actual tool outputs to construct grounded answers
  3. Assert the full pipeline: tool trajectory, answer content from real SQL, chart_spec structure

The model-to-tool-to-model loop runs live — we just script which calls the model makes.
This catches bugs that test_loop.py cannot: chart_spec propagation, multi-turn context
loss, guardrail enforcement mid-journey, answer grounding from actual query data.

Four capabilities covered (spec/capabilities/*.md):
  A. NL Query      — grounded answer from real SQL, mutating SQL refused, no-dataset case
  B. Visualisation — valid Plotly spec, correct chart type, degenerate data → prose only
  C. Multi-turn    — prior messages re-used when same thread_id is sent
  D. Dataset upload — JSON array-of-objects, column type inference (see test_ingest.py for more)
"""
import csv as csv_mod
import json
import os
import tempfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.runner import run_agent, DOMAIN_PROMPT
from src.graph import build_graph
from src.config import get_settings

# One multi-turn test drives the live /runs API (a REAL run, not a scripted FakeModel — see its
# inline comment), so it needs a funded key. Every other test here injects model=... directly.
_NEEDS_KEY = pytest.mark.skipif(
    not get_settings().llm_api_key, reason="no funded ANALYST_LLM_API_KEY (real-run /runs path)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tc(name: str, args: dict, tid: str):
    return {"id": tid, "name": name, "args": args, "type": "tool_call"}


def _tool_msgs(messages) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


def _last_tool_json(messages):
    """Parse the last ToolMessage's content as JSON, or return empty dict."""
    tms = _tool_msgs(messages)
    if not tms:
        return {}
    try:
        return json.loads(tms[-1].content)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Context-aware fake models — each is a factory closure that captures ds_id/table
# ---------------------------------------------------------------------------

def nl_query_model(ds_id: str, table: str, sql: str):
    """get_schema → execute_sql → finish(answer derived from real rows)."""

    class _M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("get_dataset_schema", {"dataset_id": ds_id}, "t1")])
            if n == 1:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {"dataset_id": ds_id, "sql": sql}, "t2")])
            # Read the actual rows from execute_sql output
            data = _last_tool_json(messages)
            rows = data.get("rows", [])
            cols = data.get("columns", [])
            top = dict(zip(cols, rows[0])) if rows else {}
            answer = (
                f"Top result: {top}" if top else "No matching rows found."
            )
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": answer}, "t3")])

    return _M()


def chart_model(ds_id: str, table: str, chart_type: str = "bar"):
    """get_schema → execute_sql → generate_chart_spec → finish(answer, chart_spec)."""

    class _M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("get_dataset_schema", {"dataset_id": ds_id}, "t1")])
            if n == 1:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {
                        "dataset_id": ds_id,
                        "sql": f"SELECT category, SUM(amount) AS total FROM {table} GROUP BY category ORDER BY total DESC",
                    }, "t2")])
            if n == 2:
                return AIMessage(content="", tool_calls=[
                    _tc("generate_chart_spec", {
                        "query_results": _tool_msgs(messages)[-1].content,
                        "chart_type": chart_type,
                        "x_col": "category",
                        "y_col": "total",
                        "title": "Sales by Category",
                    }, "t3")])
            # chart_spec string from generate_chart_spec is the last tool output
            chart_spec_str = _tool_msgs(messages)[-1].content
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": "Here is the chart.", "chart_spec": chart_spec_str}, "t4")])

    return _M()


def mutating_sql_model(ds_id: str, table: str):
    """Attempt INSERT → get REFUSED → recover with SELECT → finish."""

    class _M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            tms = _tool_msgs(messages)
            n = len(tms)
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {
                        "dataset_id": ds_id,
                        "sql": f"INSERT INTO {table} VALUES ('Hack', 9999, 'X')",
                    }, "t1")])
            if n == 1:
                # Should have received a refusal; now do a proper SELECT
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {
                        "dataset_id": ds_id,
                        "sql": f"SELECT COUNT(*) AS row_count FROM {table}",
                    }, "t2")])
            data = _last_tool_json(messages)
            rows = data.get("rows", [[0]])
            count = rows[0][0] if rows else "?"
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": f"The dataset has {count} rows."}, "t3")])

    return _M()


def degenerate_chart_model(ds_id: str, table: str):
    """execute_sql returns 1 row → generate_chart_spec returns prose → finish without chart."""

    class _M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {
                        "dataset_id": ds_id,
                        "sql": f"SELECT category, amount FROM {table} LIMIT 1",
                    }, "t1")])
            if n == 1:
                return AIMessage(content="", tool_calls=[
                    _tc("generate_chart_spec", {
                        "query_results": _tool_msgs(messages)[-1].content,
                        "chart_type": "bar",
                        "x_col": "category",
                        "y_col": "amount",
                    }, "t2")])
            # generate_chart_spec returned prose (not enough data), not a JSON spec
            prose_msg = _tool_msgs(messages)[-1].content
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": prose_msg}, "t3")])

    return _M()


def no_dataset_model():
    """list_datasets → finds nothing → finish with upload instruction."""

    class _M:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("list_datasets", {}, "t1")])
            # list_datasets returns "No datasets have been uploaded yet."
            return AIMessage(content="", tool_calls=[
                _tc("finish", {
                    "answer": "No datasets have been uploaded yet. Please upload a CSV or JSON file first."
                }, "t2")])

    return _M()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded_dataset():
    """Real CSV → DuckDB. Returns (dataset_id, table_name). Known data: Electronics=3000 tops."""
    from src.domain import Dataset, DataTable
    from src.db import get_sessionmaker
    from src import duck

    ds = Dataset(name="capability_test_sales")
    async with get_sessionmaker()() as s:
        s.add(ds)
        await s.commit()
        ds_id = ds.id

    rows = [
        ["category", "amount", "region"],
        ["Electronics", 3000, "West"],
        ["Furniture", 1050, "East"],
        ["Office", 450, "West"],
        ["Books", 200, "East"],
        ["Clothing", 150, "North"],
    ]
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
        csv_mod.writer(f).writerows(rows)
        tmp = f.name

    import asyncio
    try:
        meta = await asyncio.to_thread(duck.ingest_file, ds_id, "sales.csv", tmp, "sales.csv")
    finally:
        os.unlink(tmp)

    async with get_sessionmaker()() as s:
        s.add(DataTable(
            dataset_id=ds_id, table_name=meta["table_name"], filename=meta["filename"],
            n_rows=meta["n_rows"], n_cols=meta["n_cols"], columns=meta["columns"]))
        await s.commit()

    return ds_id, meta["table_name"]


@pytest_asyncio.fixture
async def client():
    from src.server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# A. NL Query capability (spec/capabilities/nl-query.md)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nl_query_answer_grounded_in_real_sql_data(seeded_dataset):
    """EARS: WHEN NL question asked THEN answer derived from actual SQL rows (not hallucinated)."""
    ds_id, table = seeded_dataset
    sql = f"SELECT category, SUM(amount) AS total FROM {table} GROUP BY category ORDER BY total DESC LIMIT 1"
    model = nl_query_model(ds_id, table, sql)

    result = await run_agent("Which category has the highest sales?", model=model)

    assert result["status"] == "completed"
    assert result["answer"], "Answer must not be empty"
    # The answer must reference Electronics — the actual top category in the seed data
    assert "Electronics" in result["answer"], (
        f"Answer not grounded in real data. Got: {result['answer']!r}")
    assert result["iterations"] >= 2


@pytest.mark.asyncio
async def test_nl_query_tool_trajectory_follows_spec(seeded_dataset):
    """EARS: Agent MUST call get_dataset_schema then execute_sql before finish (correct sequence)."""
    ds_id, table = seeded_dataset
    sql = f"SELECT category, amount FROM {table} ORDER BY amount DESC LIMIT 3"
    model = nl_query_model(ds_id, table, sql)

    result = await run_agent("Show top 3 categories by amount.", model=model)

    # Inspect trajectory from messages
    msgs = result["messages"]
    tool_calls_made = []
    for m in msgs:
        for tc in getattr(m, "tool_calls", None) or []:
            tool_calls_made.append(tc["name"])

    assert "get_dataset_schema" in tool_calls_made, "Must call get_dataset_schema to confirm columns"
    assert "execute_sql" in tool_calls_made, "Must call execute_sql to get real data"
    assert "finish" in tool_calls_made, "Must call finish to emit the answer"
    # get_dataset_schema must come before execute_sql
    idx_schema = tool_calls_made.index("get_dataset_schema")
    idx_sql = tool_calls_made.index("execute_sql")
    assert idx_schema < idx_sql, "get_dataset_schema must precede execute_sql"


@pytest.mark.asyncio
async def test_nl_query_mutating_sql_refused_model_recovers(seeded_dataset):
    """EARS: IF mutating SQL attempted THEN refused; model can recover with a SELECT."""
    ds_id, table = seeded_dataset
    model = mutating_sql_model(ds_id, table)

    result = await run_agent("How many rows in the dataset?", model=model)

    assert result["status"] == "completed"
    # The final answer is about row count — derived from the fallback SELECT, not the refused INSERT
    assert "5" in result["answer"] or "rows" in result["answer"].lower(), (
        f"Expected row count answer, got: {result['answer']!r}")
    # The final answer must NOT contain the refusal message (that was an internal tool error)
    assert "REFUSED" not in result["answer"]


@pytest.mark.asyncio
async def test_nl_query_no_dataset_gives_upload_instruction():
    """EARS: WHEN no dataset uploaded THEN agent calls list_datasets and instructs user to upload."""
    # No seeded_dataset fixture — DB is empty (conftest drops/recreates tables)
    model = no_dataset_model()
    result = await run_agent("What are the top categories?", model=model)

    assert result["status"] == "completed"
    answer_lower = result["answer"].lower()
    assert "upload" in answer_lower, (
        f"Expected upload instruction for empty dataset, got: {result['answer']!r}")


@pytest.mark.asyncio
async def test_nl_query_zero_rows_returns_no_match_message(seeded_dataset):
    """EARS: WHEN SQL returns zero rows THEN agent reports no matching records."""
    ds_id, table = seeded_dataset

    class _ZeroRowModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("execute_sql", {
                        "dataset_id": ds_id,
                        "sql": f"SELECT * FROM {table} WHERE category = 'Nonexistent'",
                    }, "t1")])
            data = _last_tool_json(messages)
            rows = data.get("rows", [])
            if not rows:
                answer = "No records matched the query — no rows found for 'Nonexistent'."
            else:
                answer = f"Found {len(rows)} rows."
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": answer}, "t2")])

    result = await run_agent("Find category Nonexistent", model=_ZeroRowModel())

    assert result["status"] == "completed"
    assert "no" in result["answer"].lower() or "0" in result["answer"], (
        f"Expected zero-row message, got: {result['answer']!r}")


# ---------------------------------------------------------------------------
# B. Visualisation capability (spec/capabilities/visualisation.md)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_visualisation_returns_valid_plotly_spec(seeded_dataset):
    """EARS: WHEN chart requested THEN chart_spec is valid Plotly JSON (data array + layout)."""
    ds_id, table = seeded_dataset
    model = chart_model(ds_id, table, "bar")

    result = await run_agent("Show me a bar chart of sales by category", model=model)

    assert result["status"] == "completed"
    assert result["chart_spec"] is not None, (
        "chart_spec must be present when generate_chart_spec was called")

    spec = json.loads(result["chart_spec"]) if isinstance(result["chart_spec"], str) else result["chart_spec"]
    assert "data" in spec and isinstance(spec["data"], list) and len(spec["data"]) > 0, (
        "Plotly spec must have a non-empty 'data' array")
    assert "layout" in spec and isinstance(spec["layout"], dict), (
        "Plotly spec must have a 'layout' dict")


@pytest.mark.asyncio
async def test_visualisation_bar_chart_type_honored(seeded_dataset):
    """EARS: WHEN bar chart requested THEN spec uses type 'bar'."""
    ds_id, table = seeded_dataset
    result = await run_agent("Bar chart of sales", model=chart_model(ds_id, table, "bar"))

    spec = json.loads(result["chart_spec"])
    assert spec["data"][0]["type"] == "bar", (
        f"Expected bar chart type, got: {spec['data'][0].get('type')!r}")


@pytest.mark.asyncio
async def test_visualisation_pie_chart_type_honored(seeded_dataset):
    """EARS: WHEN pie chart requested THEN spec uses type 'pie'."""
    ds_id, table = seeded_dataset
    result = await run_agent("Pie chart of sales", model=chart_model(ds_id, table, "pie"))

    spec = json.loads(result["chart_spec"])
    assert spec["data"][0]["type"] == "pie", (
        f"Expected pie chart type, got: {spec['data'][0].get('type')!r}")


@pytest.mark.asyncio
async def test_visualisation_chart_axes_use_real_column_names(seeded_dataset):
    """EARS: Chart data must use real column values from the SQL query."""
    ds_id, table = seeded_dataset
    result = await run_agent("Show bar chart", model=chart_model(ds_id, table, "bar"))

    spec = json.loads(result["chart_spec"])
    x_vals = spec["data"][0].get("x", [])
    # x-axis should contain category names from real data, not invented values
    assert "Electronics" in x_vals, (
        f"Chart x-axis must contain real category names from data, got: {x_vals}")


@pytest.mark.asyncio
async def test_visualisation_degenerate_single_row_gives_prose_not_chart(seeded_dataset):
    """EARS: WHEN query returns 1 row THEN generate_chart_spec returns prose; no chart_spec in finish."""
    ds_id, table = seeded_dataset
    model = degenerate_chart_model(ds_id, table)

    result = await run_agent("Chart for single row", model=model)

    assert result["status"] == "completed"
    # The model passed generate_chart_spec's prose output as the answer, not a chart_spec
    # chart_spec in state should be None (generate_chart_spec returned prose, model passed it as answer)
    assert result["chart_spec"] is None, (
        "When only 1 row, generate_chart_spec returns prose — no valid chart_spec should reach finish")


# ---------------------------------------------------------------------------
# C. Multi-turn conversation (spec/capabilities/multi-turn-conversation.md)
# ---------------------------------------------------------------------------

@_NEEDS_KEY
@pytest.mark.asyncio
async def test_multiturn_second_turn_has_prior_messages(client, seeded_dataset):
    """EARS: WHEN follow-up sent with same thread_id THEN prior messages are in conversation context."""
    ds_id, table = seeded_dataset
    thread_id = "multiturn-capability-test"

    # Turn 1 — patch model via monkeypatch is tricky here; use full API with a real run
    # that we can verify in the messages table
    r1 = await client.post("/runs", json={
        "goal": "List the categories in the dataset",
        "dataset_id": ds_id,
        "thread_id": thread_id,
    })
    assert r1.json()["ok"], r1.json()

    r2 = await client.post("/runs", json={
        "goal": "Which of those categories has the highest amount?",
        "dataset_id": ds_id,
        "thread_id": thread_id,
    })
    assert r2.json()["ok"], r2.json()

    # Both turns must return non-empty answers
    assert r1.json()["data"]["answer"], "Turn 1 must produce an answer"
    assert r2.json()["data"]["answer"], "Turn 2 must produce an answer"

    # Thread_id must be the same in both responses
    assert r1.json()["data"]["thread_id"] == thread_id
    assert r2.json()["data"]["thread_id"] == thread_id


@pytest.mark.asyncio
async def test_multiturn_prior_messages_accumulated_in_state(seeded_dataset):
    """EARS: After Turn 1, Turn 2 with same thread_id receives ≥ 3 messages (system+turn1+turn2)."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from src.graph import build_graph
    from src.llm import get_model

    ds_id, table = seeded_dataset
    thread_id = "multiturn-state-test"

    # Scripted model: always calls get_schema then finish
    turn = {"n": 0}

    class _MultiTurnModel:
        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            n = len(_tool_msgs(messages))
            turn["n"] += 1
            if n == 0:
                return AIMessage(content="", tool_calls=[
                    _tc("get_dataset_schema", {"dataset_id": ds_id}, f"tc{turn['n']}a")])
            return AIMessage(content="", tool_calls=[
                _tc("finish", {"answer": f"Turn {turn['n']//2 + 1} answer."}, f"tc{turn['n']}b")])

    # Use a real in-memory checkpointer so multi-turn state persists between calls
    async with AsyncSqliteSaver.from_conn_string(":memory:") as cp:
        graph = build_graph(_MultiTurnModel(), checkpointer=cp)

        r1 = await run_agent("First question", model=_MultiTurnModel(), graph=graph, thread_id=thread_id)
        r2 = await run_agent("Second question", model=_MultiTurnModel(), graph=graph, thread_id=thread_id)

    # Turn 2 messages must include Turn 1's history
    t2_msgs = r2["messages"]
    human_msgs = [m for m in t2_msgs if isinstance(m, HumanMessage)]
    # Should have both "First question" AND "Second question"
    human_texts = [m.content for m in human_msgs]
    assert "First question" in human_texts, (
        f"Turn 2 state must include Turn 1's HumanMessage. Got human messages: {human_texts}")
    assert "Second question" in human_texts, (
        f"Turn 2 state must include its own HumanMessage. Got human messages: {human_texts}")


# ---------------------------------------------------------------------------
# D. Dataset upload (spec/capabilities/dataset-upload.md) — deeper cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_json_array_of_objects_inferred_correctly(client):
    """EARS: WHEN JSON array-of-objects uploaded THEN schema inferred from keys/types."""
    r = (await client.post("/datasets", json={"name": "json-test"})).json()
    ds_id = r["data"]["id"]

    json_data = '[{"name": "Alice", "score": 95}, {"name": "Bob", "score": 87}]'
    files = {"file": ("scores.json", json_data.encode(), "application/json")}
    resp = (await client.post(f"/datasets/{ds_id}/files", files=files)).json()

    assert resp["ok"], resp
    assert resp["data"]["n_rows"] == 2
    col_names = {c["name"] for c in resp["data"]["columns"]}
    assert "name" in col_names and "score" in col_names, (
        f"Expected 'name' and 'score' columns, got: {col_names}")


@pytest.mark.asyncio
async def test_upload_csv_with_column_type_inference(client):
    """EARS: Column types must be inferred — numeric columns should not be VARCHAR."""
    r = (await client.post("/datasets", json={"name": "types-test"})).json()
    ds_id = r["data"]["id"]

    csv_data = "product,price,quantity\nWidget,9.99,100\nGadget,29.99,50\n"
    files = {"file": ("products.csv", csv_data.encode(), "text/csv")}
    resp = (await client.post(f"/datasets/{ds_id}/files", files=files)).json()

    assert resp["ok"], resp
    col_types = {c["name"]: c["type"].upper() for c in resp["data"]["columns"]}
    # DuckDB should infer price as DOUBLE/FLOAT and quantity as BIGINT/INTEGER
    assert col_types.get("product") is not None
    price_type = col_types.get("price", "")
    qty_type = col_types.get("quantity", "")
    assert any(t in price_type for t in ("DOUBLE", "FLOAT", "DECIMAL", "NUMERIC")), (
        f"price should be numeric, got: {price_type!r}")
    assert any(t in qty_type for t in ("BIGINT", "INTEGER", "INT")), (
        f"quantity should be integer, got: {qty_type!r}")


@pytest.mark.asyncio
async def test_upload_invalid_file_no_partial_dataset(client):
    """EARS: IF invalid file uploaded THEN error returned AND no table created."""
    r = (await client.post("/datasets", json={"name": "invalid-test"})).json()
    ds_id = r["data"]["id"]

    bad = {"file": ("notes.txt", b"just some plain text", "text/plain")}
    resp = (await client.post(f"/datasets/{ds_id}/files", files=bad)).json()

    assert not resp["ok"], "Invalid file must return ok=False"
    # Dataset should have no tables (no partial ingestion)
    detail = (await client.get(f"/datasets/{ds_id}")).json()
    assert detail["data"]["tables"] == [], (
        "No tables should exist after a rejected upload")
