"""Serving edge (harness/patterns/interface.md) — one runnable FastAPI app.

Routes: GET /health · POST /runs · dataset + upload endpoints · GET /traces (self-contained, no-JS viewer).
One envelope everywhere: ok(data) / err(msg). The /traces viewer reads the spans table the loop writes
(harness/patterns/observability-and-evals.md).
"""
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from . import duck
from .db import Run, Span, get_sessionmaker, init_db
from .domain import Conversation, DataTable, Dataset
from .runner import run_agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()                                  # create_all — sqlite local-first
    yield


app = FastAPI(title="DataChat", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_methods=["*"], allow_headers=["*"],
)


def ok(data):
    return {"ok": True, "data": data}


def err(msg):
    return {"ok": False, "error": msg}


# ----- run the agent -----------------------------------------------------------------
class RunIn(BaseModel):
    goal: str
    dataset_id: str | None = None
    conversation_id: str | None = None


@app.get("/health")
async def health():
    return ok({"status": "alive"})


@app.post("/runs")
async def create_run(body: RunIn):
    try:
        r = await run_agent(body.goal, dataset_id=body.dataset_id, conversation_id=body.conversation_id)
        return ok({k: r[k] for k in
                   ("run_id", "answer", "iterations", "dataset_id", "conversation_id", "status", "charts")})
    except Exception as e:                            # surface key/model failures as JSON, not a 500
        return err(str(e))


# ----- datasets + upload (ingest-dataset capability) ---------------------------------
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
async def list_datasets():
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
        # ingest is sync/blocking (DuckDB) — keep it off the event loop
        import asyncio
        meta = await asyncio.to_thread(
            duck.ingest_file, dataset_id, file.filename or "table", tmp.name, file.filename or "table")
    except ValueError as e:                           # malformed/unsupported → clean error, prior tables intact
        return err(str(e))
    finally:
        os.unlink(tmp.name)

    async with get_sessionmaker()() as s:
        s.add(DataTable(
            dataset_id=dataset_id, table_name=meta["table_name"], filename=meta["filename"],
            n_rows=meta["n_rows"], n_cols=meta["n_cols"], columns=meta["columns"]))
        await s.commit()
    return ok(meta)


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


# ----- conversations (multi-turn threads) --------------------------------------------
class ConversationIn(BaseModel):
    dataset_id: str | None = None
    title: str | None = None


@app.post("/conversations")
async def create_conversation(body: ConversationIn):
    conv = Conversation(dataset_id=body.dataset_id, title=body.title or "New conversation")
    async with get_sessionmaker()() as s:
        s.add(conv)
        await s.commit()
        cid = conv.id
    return ok({"id": cid, "dataset_id": body.dataset_id})


# ----- /traces viewer (server-rendered HTML, no JS) ----------------------------------
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
        ans = f" — {_esc(r.answer)}" if r.answer else ""
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
                f"<pre style='margin:2px 0;color:#374151;white-space:pre-wrap'>{_esc(sp.attributes)}</pre>{err_html}</div>")
    body = "".join(rows) or "<p>No runs yet. POST a goal to /runs.</p>"
    return ("<html><body style='font-family:system-ui;max-width:900px;margin:2rem auto'>"
            f"<h1>DataChat — Traces</h1>{body}</body></html>")


@app.get("/traces", response_class=HTMLResponse)
async def traces():
    return await _traces_html()
