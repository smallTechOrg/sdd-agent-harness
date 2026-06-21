"""Serving edge (harness/patterns/interface.md) — one runnable FastAPI app.

Routes:
  GET  /health                  — liveness probe
  POST /runs                    — full run, returns answer + run_id + thread_id
  POST /runs/stream             — SSE token stream (same run, real-time tokens)
  POST /upload                  — multipart file upload (CSV / JSON)
  GET  /datasets                — list ingested datasets
  GET  /datasets/{id}           — dataset detail + schema
  GET  /traces                  — self-contained run/span timeline (no JS)

One envelope: ok(data) / err(msg). AsyncSqliteSaver checkpointer is opened in lifespan and shared
across all runs so multi-turn thread_id state is persistent within the session.
"""
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from . import duck
from .db import Run, Span, get_sessionmaker, init_db
from .domain import DataTable, Dataset
from .runner import run_agent

_graph = None  # compiled graph with persistent checkpointer; None until lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    await init_db()
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from .graph import build_graph
        from .llm import get_model
        cp = AsyncSqliteSaver.from_conn_string("checkpoints.db")
        await cp.__aenter__()
        try:
            _graph = build_graph(get_model(), checkpointer=cp)
        except RuntimeError:
            # no API key at startup — tests inject a FakeModel via run_agent(model=..., graph=None)
            _graph = None
        yield
        await cp.__aexit__(None, None, None)
    except Exception:
        yield
    finally:
        _graph = None


app = FastAPI(title="Data Analyst Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def ok(data):
    return {"ok": True, "data": data}


def err(msg):
    return {"ok": False, "error": msg}


# --- run the agent -------------------------------------------------------------------

class RunIn(BaseModel):
    goal: str
    dataset_id: str | None = None
    thread_id: str | None = None


@app.get("/health")
async def health():
    from .config import get_settings
    s = get_settings()
    stub = not bool(s.llm_api_key)
    return ok({"status": "alive", "stub_mode": stub})


@app.post("/runs")
async def create_run(body: RunIn):
    try:
        r = await run_agent(
            body.goal,
            dataset_id=body.dataset_id,
            thread_id=body.thread_id,
            graph=_graph,
        )
        return ok({k: r[k] for k in ("run_id", "thread_id", "answer", "chart_spec",
                                      "input_tokens", "output_tokens", "cost_usd",
                                      "iterations", "dataset_id", "status")})
    except Exception as e:
        return err(str(e))


@app.post("/runs/stream")
async def stream_run(body: RunIn):
    """SSE token stream — forward on_chat_model_stream chunks then the final done event.

    Uses run_agent under the hood so runs are persisted (Run + Message rows created), then
    re-runs the graph with astream_events to emit tokens. The done event carries the full
    result (answer + chart_spec + run_id) so the UI can render charts and trace links.
    """
    from .graph import build_graph
    from .llm import get_model

    try:
        graph = _graph or build_graph(get_model())
    except RuntimeError as e:
        return err(str(e))

    thread_id = body.thread_id or str(uuid.uuid4())

    async def gen():
        from langchain_core.messages import HumanMessage, SystemMessage
        from .runner import DOMAIN_PROMPT, _dataset_context, _load_prior_messages
        run_id = str(uuid.uuid4())
        ds_ctx = await _dataset_context(body.dataset_id)
        system_content = DOMAIN_PROMPT + ds_ctx
        prior = await _load_prior_messages(graph, thread_id)
        if prior:
            # Always refresh the system message so the current dataset context is applied,
            # even when resuming a conversation that started under a different dataset.
            non_sys = [m for m in prior if not isinstance(m, SystemMessage)]
            msgs = [SystemMessage(content=system_content)] + non_sys + [HumanMessage(content=body.goal)]
        else:
            msgs = [SystemMessage(content=system_content), HumanMessage(content=body.goal)]
        state = {
            "messages": msgs,
            "iterations": 0, "answer": None, "chart_spec": None, "run_id": run_id,
        }
        cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        answer = ""
        chart_spec = None
        total_input_tokens = 0
        total_output_tokens = 0
        try:
            async for ev in graph.astream_events(state, config=cfg, version="v2"):
                if ev["event"] == "on_chat_model_stream":
                    chunk = ev["data"].get("chunk")
                    tok = chunk.content if chunk else ""
                    if isinstance(tok, list):
                        tok = " ".join(b.get("text", "") for b in tok if isinstance(b, dict))
                    if tok:
                        yield f"data: {json.dumps({'token': tok})}\n\n"
                elif ev["event"] == "on_chat_model_end":
                    msg = (ev.get("data", {}) or {}).get("output")
                    if msg:
                        u = getattr(msg, "usage_metadata", None) or {}
                        total_input_tokens += u.get("input_tokens", 0)
                        total_output_tokens += u.get("output_tokens", 0)
                elif ev["event"] == "on_chain_end" and ev.get("name") == "finalize":
                    out = (ev.get("data", {}).get("output") or {})
                    answer = out.get("answer", "")
                    chart_spec = out.get("chart_spec") or None
            yield f"data: {json.dumps({'done': True, 'answer': answer, 'chart_spec': chart_spec, 'run_id': run_id, 'thread_id': thread_id, 'input_tokens': total_input_tokens, 'output_tokens': total_output_tokens})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        # Persist the run row for /traces (best-effort, errors do not fail the stream)
        try:
            from .runner import _calc_cost, _upsert_thread
            from .db import Run, get_sessionmaker
            cost = _calc_cost(total_input_tokens, total_output_tokens)
            async with get_sessionmaker()() as s:
                s.add(Run(id=run_id, goal=body.goal, status="completed", answer=answer,
                          thread_id=thread_id, input_tokens=total_input_tokens,
                          output_tokens=total_output_tokens, cost_usd=cost))
                await s.commit()
            await _upsert_thread(thread_id, body.dataset_id, body.goal, total_input_tokens, total_output_tokens, cost)
        except Exception:
            pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- datasets + upload ---------------------------------------------------------------

class DatasetIn(BaseModel):
    name: str


@app.post("/datasets")
async def create_dataset(body: DatasetIn):
    ds = Dataset(name=body.name)
    async with get_sessionmaker()() as s:
        s.add(ds)
        await s.commit()
        ds_id = ds.id
    return ok({"id": ds_id, "name": body.name})


@app.get("/datasets")
async def list_datasets_endpoint():
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Dataset).order_by(Dataset.created_at.desc()))).scalars().all()
    return ok([{"id": d.id, "name": d.name} for d in rows])


@app.post("/datasets/{dataset_id}/files")
async def upload_file(dataset_id: str, file: UploadFile):
    async with get_sessionmaker()() as s:
        ds = await s.get(Dataset, dataset_id)
    if ds is None:
        return err(f"dataset {dataset_id} not found")

    suffix = os.path.splitext(file.filename or "upload")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await file.read())
        tmp.close()
        import asyncio
        meta = await asyncio.to_thread(
            duck.ingest_file, dataset_id, file.filename or "table", tmp.name, file.filename or "table")
    except ValueError as e:
        return err(str(e))
    finally:
        os.unlink(tmp.name)

    async with get_sessionmaker()() as s:
        s.add(DataTable(
            dataset_id=dataset_id, table_name=meta["table_name"], filename=meta["filename"],
            n_rows=meta["n_rows"], n_cols=meta["n_cols"], columns=meta["columns"]))
        await s.commit()
    return ok(meta)


@app.post("/upload")
async def upload_files(files: list[UploadFile]):
    """Convenience: create dataset + upload files in one shot. Returns list of per-file results."""
    results = []
    for file in files:
        ds_name = os.path.splitext(file.filename or "upload")[1 :]  # use filename stem as dataset name
        ds_name = os.path.splitext(file.filename or "upload")[0]
        async with get_sessionmaker()() as s:
            ds = Dataset(name=ds_name)
            s.add(ds)
            await s.commit()
            ds_id = ds.id
        suffix = os.path.splitext(file.filename or "upload")[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(await file.read())
            tmp.close()
            import asyncio
            meta = await asyncio.to_thread(
                duck.ingest_file, ds_id, file.filename or "table", tmp.name, file.filename or "table")
        except ValueError as e:
            results.append({"filename": file.filename, "error": str(e)})
            continue
        finally:
            os.unlink(tmp.name)
        async with get_sessionmaker()() as s:
            s.add(DataTable(
                dataset_id=ds_id, table_name=meta["table_name"], filename=meta["filename"],
                n_rows=meta["n_rows"], n_cols=meta["n_cols"], columns=meta["columns"]))
            await s.commit()
        results.append({"dataset_id": ds_id, "name": ds_name, **meta})
    return ok(results)


@app.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    async with get_sessionmaker()() as s:
        ds = await s.get(Dataset, dataset_id)
        if ds is None:
            return err(f"dataset {dataset_id} not found")
        tables = (await s.execute(
            select(DataTable).where(DataTable.dataset_id == dataset_id))).scalars().all()
    return ok({"id": ds.id, "name": ds.name,
               "tables": [{"table_name": t.table_name, "filename": t.filename,
                           "n_rows": t.n_rows, "n_cols": t.n_cols, "columns": t.columns} for t in tables]})


# --- sessions (threads) + spans ------------------------------------------------------

@app.get("/sessions")
async def list_sessions():
    from .domain import Thread, Dataset
    async with get_sessionmaker()() as s:
        threads = (await s.execute(
            select(Thread).order_by(Thread.last_active_at.desc())
        )).scalars().all()
        ds_ids = [t.dataset_id for t in threads if t.dataset_id]
        ds_map: dict[str, str] = {}
        if ds_ids:
            rows = (await s.execute(select(Dataset).where(Dataset.id.in_(ds_ids)))).scalars().all()
            ds_map = {d.id: d.name for d in rows}
    return ok([{
        "id": t.id,
        "title": t.title or "(untitled)",
        "dataset_id": t.dataset_id,
        "dataset_name": ds_map.get(t.dataset_id or "", ""),
        "run_count": t.run_count,
        "total_input_tokens": t.total_input_tokens,
        "total_output_tokens": t.total_output_tokens,
        "total_cost_usd": t.total_cost_usd,
        "created_at": t.created_at.isoformat(),
        "last_active_at": t.last_active_at.isoformat(),
    } for t in threads])


@app.get("/sessions/{thread_id}")
async def get_session(thread_id: str):
    from .domain import Thread
    async with get_sessionmaker()() as s:
        thread = await s.get(Thread, thread_id)
        if thread is None:
            return err(f"session {thread_id!r} not found")
        runs = (await s.execute(
            select(Run).where(Run.thread_id == thread_id).order_by(Run.created_at)
        )).scalars().all()
    return ok({
        "id": thread.id,
        "title": thread.title or "(untitled)",
        "dataset_id": thread.dataset_id,
        "run_count": thread.run_count,
        "total_input_tokens": thread.total_input_tokens,
        "total_output_tokens": thread.total_output_tokens,
        "total_cost_usd": thread.total_cost_usd,
        "created_at": thread.created_at.isoformat(),
        "last_active_at": thread.last_active_at.isoformat(),
        "runs": [{
            "id": r.id,
            "goal": r.goal,
            "status": r.status,
            "answer": (r.answer or "")[:200],
            "iterations": r.iterations,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "created_at": r.created_at.isoformat(),
        } for r in runs],
    })


@app.get("/runs/{run_id}/spans")
async def get_run_spans(run_id: str):
    async with get_sessionmaker()() as s:
        spans = (await s.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.start_ms)
        )).scalars().all()
    return ok([{
        "id": sp.id,
        "name": sp.name,
        "kind": sp.kind,
        "duration_ms": sp.duration_ms,
        "attributes": sp.attributes or {},
    } for sp in spans])


@app.get("/datasets/{dataset_id}/summary")
async def dataset_summary(dataset_id: str):
    """Column stats for the dashboard: numeric min/max/avg, categorical top values."""
    from . import duck
    import asyncio
    async with get_sessionmaker()() as s:
        ds = await s.get(Dataset, dataset_id)
        if ds is None:
            return err(f"dataset {dataset_id} not found")

    try:
        schema = await asyncio.to_thread(duck.dataset_schema, dataset_id)
    except Exception as e:
        return err(str(e))

    col_stats: dict = {}
    for table in schema.get("tables", []):
        tname = table["table"]
        stats: dict = {}
        for col in table["columns"]:
            cname = col["name"]
            ctype = col["type"].upper()
            try:
                if any(t in ctype for t in ("INT", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "REAL")):
                    r = duck.run_query(dataset_id, f'SELECT MIN("{cname}") as mn, MAX("{cname}") as mx, AVG("{cname}") as avg, COUNT(*) - COUNT("{cname}") as nulls FROM "{tname}"', 1)
                    if not r.get("error") and r.get("rows"):
                        mn, mx, avg, nulls = r["rows"][0]
                        stats[cname] = {"type": "numeric", "min": mn, "max": mx, "avg": round(avg or 0, 2), "null_count": nulls}
                else:
                    r = duck.run_query(dataset_id, f'SELECT "{cname}", COUNT(*) as cnt FROM "{tname}" GROUP BY "{cname}" ORDER BY cnt DESC LIMIT 10', 10)
                    if not r.get("error") and r.get("rows"):
                        stats[cname] = {"type": "categorical", "top_values": [[row[0], row[1]] for row in r["rows"]]}
            except Exception:
                pass
        if stats:
            col_stats[tname] = stats
    return ok({"id": ds.id, "name": ds.name, "tables": schema.get("tables", []), "col_stats": col_stats})


# --- /traces viewer (server-rendered HTML, no JS) ------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/traces")


KIND_COLOR = {"INTERNAL": "#6b7280", "LLM": "#2563eb", "TOOL": "#16a34a"}


def _esc(x) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _traces_html() -> str:
    async with get_sessionmaker()() as s:
        runs = (await s.execute(select(Run).order_by(Run.created_at.desc()))).scalars().all()
        spans = (await s.execute(select(Span).order_by(Span.start_ms))).scalars().all()
    by_run: dict[str, list[Span]] = {}
    for sp in spans:
        by_run.setdefault(sp.run_id, []).append(sp)
    rows = []
    for r in runs:
        rspans = by_run.get(r.id, [])
        maxd = max((sp.duration_ms for sp in rspans), default=1) or 1
        ans = f" — {_esc(r.answer[:200])}" if r.answer else ""
        rows.append(f"<h2>{_esc(r.goal)} <small>[{_esc(r.status)}] · {len(rspans)} spans</small></h2>"
                    f"<div style='color:#374151;margin:-6px 0 6px'>{ans}</div>")
        for sp in rspans:
            color = KIND_COLOR.get(sp.kind, "#6b7280")
            bar = max(2, int(200 * sp.duration_ms / maxd))
            err_attr = sp.attributes.get("error") if isinstance(sp.attributes, dict) else None
            err_html = f"<div style='color:#dc2626'>{_esc(err_attr)}</div>" if err_attr else ""
            rows.append(
                f"<div style='margin:4px 0'>"
                f"<span style='background:{color};color:#fff;padding:1px 6px;border-radius:4px'>{_esc(sp.kind)}</span> "
                f"<b>{_esc(sp.name)}</b> "
                f"<span style='display:inline-block;height:8px;width:{bar}px;background:{color};vertical-align:middle'></span> "
                f"{sp.duration_ms}ms"
                f"<pre style='margin:2px 0;color:#374151;white-space:pre-wrap'>{_esc(sp.attributes)}</pre>"
                f"{err_html}</div>")
    body = "".join(rows) or "<p>No runs yet. POST a goal to /runs.</p>"
    return ("<html><body style='font-family:system-ui;max-width:900px;margin:2rem auto'>"
            f"<h1>Data Analyst Agent — Traces</h1>{body}</body></html>")


@app.get("/traces", response_class=HTMLResponse)
async def traces():
    return await _traces_html()
