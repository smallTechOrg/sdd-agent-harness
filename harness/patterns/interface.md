# Pattern: Interface / serving (Layer 10)

How the agent reaches the outside world: an async FastAPI app exposing `/health`, `POST /runs`, and the
built-in `/traces` viewer. **Generate this fresh at build time**, pinning the *current* `fastapi` /
`uvicorn` (check the latest first — a guessed/old version 404s). The code below is proven working.

The graph and loop come from `patterns/react-agent.md`; the span emission feeding the viewer from
`patterns/observability-and-evals.md`; the runtime model from `patterns/model-and-providers.md`. This
recipe owns the serving edge **and** the self-contained `/traces` viewer (one runnable `server.py`).

## Contract
- `GET /health` → `{"ok": true}` — the liveness probe the demo gate hits.
- `POST /runs {"goal": "...", "session_id"?: "...", "data"?: "..."}` → runs the agent, returns the `ok()`
  envelope with the answer + run id. `session_id` (optional) ties follow-up turns to one session/thread —
  the two-turn gate (`workflows/gates.md` check 5) posts the same `session_id` on Q1 and Q2; it is persisted
  as `thread_id` and keys the session-scoped resource store (`patterns/persistence.md`). `data` (optional) is
  the **data-ingest seam**: a resource an "analyze an uploaded X" agent needs (a CSV/JSON/text blob). When
  present it is loaded into the session store **before** the run, so a data agent's Q1 carries the resource
  and Q2 reuses it from the session (no re-upload) — without this seam a data agent's gate Q1 hits an empty
  session and the outcome eval fails on a "no data is loaded" non-answer. Wire only when a capability ingests
  a resource (`C-SESSION-SCOPE`); a key-free/own-data agent leaves it unset. For large/binary uploads use a
  separate `POST /sessions/{id}/resource` (multipart) with the same load → session-store contract.
- `GET /` → redirect to `/traces`; `GET /traces` → server-rendered timeline (no JS). The **`run_id` is
  rendered verbatim** in each run's drill-down (as the `<details id>` and as visible muted text) — gate
  check 8 (`workflows/gates.md`) greps it to prove the run is observable; a viewer that omits it false-REDs.
- Port **8001** (override `APP_PORT`). One envelope shape everywhere: `ok(data)` / `api_error(code, …)` —
  every failure is a coded JSON error, never an error page or a raw 500.

## Code — `agent/runner.py` (proven, verbatim)
Drives one run end-to-end: create the `Run`, build the graph, seed the domain system prompt + goal, invoke
under the `invoke_agent` span, persist messages + outcome. `run_id` is returned so the caller can deep-link
into `/traces`.
```python
import uuid
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from .config import get_settings
from .db import Message, Run, Span, get_sessionmaker
from .graph import build_graph
from .llm import get_model
from .observability import span

DOMAIN_PROMPT = (  # the spec-writer overwrites this from spec/product.md (domain instructions)
    "You are a focused task agent. Use the tools available. Call finish when you have the answer."
)

async def run_agent(goal: str, model=None, run_id: str | None = None,
                    session_id: str | None = None, checkpointer=None) -> dict:
    settings = get_settings()
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()

    async with get_sessionmaker()() as s:
        # session_id is the multi-turn thread key (= thread_id); it scopes the session resource store
        # (patterns/persistence.md) so a follow-up turn sees Q1's loaded resource.
        s.add(Run(id=run_id, goal=goal, status="running", iterations=0, thread_id=session_id))
        await s.commit()

    graph = build_graph(model, checkpointer=checkpointer)   # ONE compile; saver = short-term memory
    config = {"recursion_limit": 50}
    # SHORT-TERM MEMORY: with a checkpointer + a session_id, reload this thread's transcript and compose the
    # seed as prior(stale SystemMessage stripped) + fresh SystemMessage + new goal. There is no add_messages
    # reducer, so the runner — not the channel — owns the merge (patterns/react-agent.md WARNING).
    prior: list = []
    if checkpointer is not None and session_id:
        config["configurable"] = {"thread_id": session_id}
        cp = await checkpointer.aget(config)                 # raw checkpoint dict, or None on turn 1
        if cp:
            saved = cp["channel_values"].get("messages", [])
            prior = [m for m in saved if not isinstance(m, SystemMessage)]   # drop the stale system prompt
    state = {
        "messages": prior + [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content=goal)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }
    # SESSION CONTEXT FOR TOOLS: the loop (patterns/react-agent.md tools_node) calls tools with ONLY the
    # model-supplied args, so a session-resource query tool can't get session_id as a parameter without the
    # model hallucinating it. Set it on a ContextVar around ainvoke; the tool reads current_session_id.get()
    # (patterns/persistence.md § read path). The import is guarded so this same runner works for a key-free
    # agent that never generates sessions.py (C-SESSION-SCOPE OFF). Always reset in finally.
    try:
        from .sessions import current_session_id      # generated for data agents (C-SESSION-SCOPE) only
    except ImportError:
        current_session_id = None
    token = current_session_id.set(session_id) if current_session_id is not None else None
    try:
        async with span(run_id, "invoke_agent", "INTERNAL", goal=goal):
            result = await graph.ainvoke(state, config=config)
    finally:
        if token is not None:
            current_session_id.reset(token)

    async with get_sessionmaker()() as s:
        for m in result["messages"]:
            role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
            content = m.content if isinstance(m.content, str) else str(m.content)
            s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role, content=content))
        # sum this run's LLM-span tokens into first-class cost columns (the /traces dashboard reads these)
        spans = (await s.execute(select(Span).where(Span.run_id == run_id, Span.kind == "LLM"))).scalars().all()
        tok_in = sum((sp.attributes or {}).get("tokens", {}).get("input", 0) for sp in spans)
        tok_out = sum((sp.attributes or {}).get("tokens", {}).get("output", 0) for sp in spans)
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]
        run.input_tokens, run.output_tokens = tok_in, tok_out
        run.cost_usd = (tok_in * settings.price_in + tok_out * settings.price_out) / 1_000_000  # per-1M rates (config.py)
        await s.commit()

    # `status` rides in the response dict (not just the DB row) so the two-turn gate can assert
    # `.data.status == "completed"` straight off the ok() envelope — workflows/gates.md check 5.
    return {"run_id": run_id, "thread_id": session_id, "status": "completed",
            "answer": result["answer"], "iterations": result["iterations"],
            "messages": result["messages"]}
```

## Code — `agent/server.py` (proven, verbatim — self-contained, the `/traces` dashboard lives here)
The whole serving edge in one runnable file: `app = FastAPI(lifespan=...)` plus `/health`, `POST /runs`,
and the inline `/traces` **observability dashboard** (server-rendered HTML, no JS, no Docker, no signup).
The span emission feeding it is owned by `patterns/observability-and-evals.md`; the rendering lives here.
`KIND_COLOR` maps the three span kinds the loop emits: `INTERNAL` (top run span), `LLM`, `TOOL`.

`/traces` is built for a **non-technical reader**, not a developer reading a flame graph. It leads with an
**overview band** — total runs, success rate, total + average cost, total tokens, average answer time — then
a per-run **drill-down** that narrates each step in plain English ("Asked the AI model — 1.2s", "Looked up
the refund policy — 0.3s") with the technical span name available but secondary. The whole point: a person
who can't read code can still see *what the agent did, whether it worked, and what it cost*.
```python
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from .config import validate_required_config
from .db import get_sessionmaker, init_db, Run, Span
from .runner import run_agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_required_config()               # fail LOUD at boot if required config is missing (config.py)
    await init_db()                          # create_all — sqlite local-first
    # SHORT-TERM (multi-turn) MEMORY: open ONE AsyncSqliteSaver for the process and keep it on app state, so
    # follow-up turns on the same session_id resume the thread (patterns/memory.md, react-agent.md). This is
    # what makes the two-turn gate's Q2 see Q1's context (workflows/gates.md check 5). A headless single-shot
    # product can leave app.state.checkpointer = None.
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver   # pip: langgraph-checkpoint-sqlite
    cm = AsyncSqliteSaver.from_conn_string("checkpoints.db")
    app.state.checkpointer = await cm.__aenter__()
    try:
        yield
    finally:
        await cm.__aexit__(None, None, None)

app = FastAPI(title="agent", lifespan=lifespan)

# One envelope shape EVERYWHERE: ok(data) on success, api_error(code, ...) on failure — never an error page,
# never a raw 500 stacktrace a non-tech user has to decode.
def ok(data):
    return {"ok": True, "data": data}

class ApiError(Exception):
    def __init__(self, code: str, msg: str = "", status: int = 500):
        self.code, self.msg, self.status = code, msg or code, status

def api_error(code: str, msg: str = "", status: int = 500) -> ApiError:
    return ApiError(code, msg, status)

@app.exception_handler(ApiError)
async def _api_error_handler(_req, exc: ApiError):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": False, "error": {"code": exc.code, "message": exc.msg}}, status_code=exc.status)

class RunIn(BaseModel):
    goal: str
    session_id: str | None = None        # optional — ties follow-up turns to one session/thread (two-turn gate)
    data: str | None = None              # optional DATA-INGEST seam — a resource ("analyze an uploaded X")
                                         # loaded into the session store BEFORE the run; Q2 reuses it. Wire
                                         # only when a capability ingests a resource (C-SESSION-SCOPE).

@app.get("/health")
async def health():
    return ok({"status": "alive"})

@app.post("/runs")
async def create_run(request: Request, body: RunIn):
    try:
        # DATA-INGEST seam: if a resource came with this turn, load it into the session store BEFORE the run
        # so the tools see it — and so Q2 on the same session reuses it (persistence.md § session-scoped).
        # Generate `load_resource` only when a capability ingests data (C-SESSION-SCOPE); a key-free/own-data
        # agent omits the `data` field and this block. Example loader (CSV → DataFrame) below the server code.
        # If `data` arrives WITHOUT a session_id, auto-mint one server-side so the upload is NEVER silently
        # dropped: a client that POSTs the resource on a fresh thread (no session_id yet) would otherwise get a
        # 200 with a "no <resource> loaded" wrong answer — a load_resource keyed on `session_id is not None`
        # silently skips. Minting one (and threading it through) makes the upload always take effect.
        if body.data is not None:
            from .sessions import load_resource          # generated for data agents only
            if body.session_id is None:
                body.session_id = uuid.uuid4().hex       # never lose the upload — mint a session for it
            load_resource(body.session_id, body.data)
        # session_id threads through to the Run's thread_id + the session resource store (persistence.md);
        # the shared checkpointer (app state) gives Q2 on the same session Q1's context (memory.md).
        # READ IT WITH getattr, NOT `request.app.state.checkpointer` — the checkpointer is set in the LIFESPAN,
        # and httpx's ASGITransport (the keyless full-stack contract test, observability-and-evals.md
        # tests/test_api_flow.py) does NOT run the lifespan, so `app.state.checkpointer` is unset there and a
        # bare attribute access raises AttributeError → caught below as api_error("RUN_FAILED") → every faithful
        # in-process contract test 500s (HARDENING-LOG iter 9). getattr(..., None) degrades to a single-turn run
        # (no short-term memory) in-process while the live server (which DOES run the lifespan) keeps multi-turn.
        checkpointer = getattr(request.app.state, "checkpointer", None)
        return ok(await run_agent(body.goal, session_id=body.session_id,
                                  checkpointer=checkpointer))   # dict → straight into ok()
    except ApiError:
        raise                                    # already coded — the handler renders the JSON envelope
    except Exception as e:                        # surface key/model failures as a CODED JSON error, not a 500 stacktrace
        raise api_error("RUN_FAILED", str(e), status=500)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/traces")

KIND_COLOR = {"INTERNAL": "#6b7280", "LLM": "#2563eb", "TOOL": "#16a34a"}
# plain-English label for each span kind — what a non-coder reads instead of the technical name
KIND_PLAIN = {"INTERNAL": "Run step", "LLM": "Asked the AI model", "TOOL": "Used a tool"}

def _esc(x) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _plain_step(sp) -> str:
    """Turn a span name into a human sentence. `execute_tool.search_docs` -> 'Used a tool: search docs'."""
    if sp.name.startswith("execute_tool."):
        return "Used a tool: " + sp.name.removeprefix("execute_tool.").replace("_", " ")
    if sp.kind == "LLM":
        return "Asked the AI model"
    if sp.name == "invoke_agent":
        return "Ran the agent"
    return KIND_PLAIN.get(sp.kind, sp.name)

async def _traces_html() -> str:
    async with get_sessionmaker()() as s:
        runs = (await s.execute(select(Run).order_by(Run.created_at.desc()))).scalars().all()
        spans = (await s.execute(select(Span).order_by(Span.start_ms))).scalars().all()
    by_run: dict[str, list[Span]] = {}
    for sp in spans:
        by_run.setdefault(sp.run_id, []).append(sp)

    # --- OVERVIEW BAND: the at-a-glance numbers a non-technical reader wants first --------------------
    total = len(runs)
    ok_runs = sum(1 for r in runs if r.status == "completed")
    total_cost = sum(r.cost_usd or 0 for r in runs)
    total_tokens = sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in runs)
    def _run_ms(rid):                                    # wall time of a run = its widest span (the invoke_agent span)
        sp = by_run.get(rid) or []
        return max((s.end_ms - s.start_ms for s in sp), default=0)
    avg_ms = (sum(_run_ms(r.id) for r in runs) / total) if total else 0
    def _card(label, value):
        return (f"<div style='flex:1;min-width:120px;background:#f9fafb;border:1px solid #e5e7eb;"
                f"border-radius:8px;padding:12px'><div style='font-size:22px;font-weight:700'>{value}</div>"
                f"<div style='color:#6b7280;font-size:13px'>{_esc(label)}</div></div>")
    overview = (
        "<div style='display:flex;gap:12px;flex-wrap:wrap;margin:0 0 24px'>"
        + _card("runs", total)
        + _card("succeeded", f"{ok_runs}/{total}" + (f" ({100*ok_runs//total}%)" if total else ""))
        + _card("total cost", f"${total_cost:.4f}")
        + _card("avg cost / run", f"${(total_cost/total if total else 0):.4f}")
        + _card("total tokens", f"{total_tokens:,}")
        + _card("avg answer time", f"{avg_ms/1000:.1f}s")
        + "</div>"
    )

    # --- DRILL-DOWN: one collapsible card per run, each step narrated in plain English ----------------
    rows = []
    for r in runs:
        rspans = by_run.get(r.id, [])
        maxd = max((sp.duration_ms for sp in rspans), default=1) or 1
        badge = "#16a34a" if r.status == "completed" else "#dc2626" if r.status == "error" else "#d97706"
        meta = (f"<span style='color:{badge};font-weight:600'>{_esc(r.status)}</span> · "
                f"{len(rspans)} steps · ${r.cost_usd or 0:.4f} · "
                f"{(r.input_tokens or 0)+(r.output_tokens or 0):,} tokens")
        steps = []
        for sp in rspans:
            color = KIND_COLOR.get(sp.kind, "#6b7280")
            bar = max(2, int(200 * sp.duration_ms / maxd))
            err_attr = sp.attributes.get("error") if isinstance(sp.attributes, dict) else None
            err_html = f"<div style='color:#dc2626;margin-left:8px'>⚠ {_esc(err_attr)}</div>" if err_attr else ""
            steps.append(
                f"<div style='margin:4px 0'>"
                f"<b>{_esc(_plain_step(sp))}</b> "
                f"<span style='display:inline-block;height:8px;width:{bar}px;background:{color};vertical-align:middle'></span> "
                f"<span style='color:#6b7280'>{sp.duration_ms/1000:.2f}s</span> "
                f"<span style='color:#9ca3af;font-size:12px'>{_esc(sp.name)}</span>"
                f"<pre style='margin:2px 0 2px 8px;color:#374151;font-size:12px;white-space:pre-wrap'>{_esc(sp.attributes)}</pre>"
                f"{err_html}</div>"
            )
        # The run_id MUST appear VERBATIM in the rendered HTML — gate check 8 greps it
        # (`workflows/gates.md` demo_gate.sh: `curl /traces | grep -q "$RUN_ID"`). It is emitted as the
        # <details id> AND as visible muted text so the drill-down is deep-linkable and the gate's
        # "proves it ran" needle resolves. Do not remove or escape it away — check 8 false-REDs without it.
        rows.append(
            f"<details id='{_esc(r.id)}' style='border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin:0 0 12px'{' open' if r is runs[0] else ''}>"
            f"<summary style='cursor:pointer'><b>{_esc(r.goal)}</b> "
            f"<span style='color:#9ca3af;font-size:12px;font-weight:400'>{_esc(r.id)}</span>"
            f"<br><small>{meta}</small></summary>"
            f"<div style='margin-top:8px'>{''.join(steps) or '<i>no steps recorded</i>'}</div></details>"
        )
    body = overview + ("".join(rows) or "<p>No runs yet. POST a goal to /runs.</p>")
    return (f"<html><body style='font-family:system-ui;max-width:900px;margin:2rem auto'>"
            f"<h1>Observability dashboard</h1>"
            f"<p style='color:#6b7280'>Every run the agent did, in plain English — what it did, whether it worked, what it cost.</p>"
            f"{body}</body></html>")

@app.get("/traces", response_class=HTMLResponse)
async def traces():
    return await _traces_html()              # server-rendered HTML, no JS
```

## Code — `agent/__main__.py` (proven, verbatim)
```python
import uvicorn
from .config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("agent.server:app", host="0.0.0.0", port=s.port, reload=False)
```
Run it: `python -m agent` → `http://localhost:8001`. `GET /health` is the demo gate's liveness check;
the deploy artifact serves the same app (`patterns/durability.md`, deploy ladder).

## SSE token streaming (sketch — add when the UI wants live tokens)
`POST /runs` returns the whole answer; for a typing-cursor UX stream tokens over **Server-Sent Events**.
Stream from `graph.astream_events` (LangGraph emits `on_chat_model_stream` chunks) and forward each token
as an SSE `data:` line. One extra endpoint, no protocol change to the rest:
```python
import json
from fastapi.responses import StreamingResponse

@app.post("/runs/stream")
async def stream_run(body: RunIn):
    async def gen():
        async for ev in stream_agent(body.goal):        # wraps graph.astream_events(..., version="v2")
            if ev["event"] == "on_chat_model_stream" and (tok := ev["data"]["chunk"].content):
                yield f"data: {json.dumps({'token': tok})}\n\n"
            elif ev["event"] == "on_chain_end" and ev["name"] == "finalize":
                yield f"data: {json.dumps({'done': True, 'answer': ev['data']['output']['answer']})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```
Headers that bite in prod: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (disable proxy buffering).
Client reads with `EventSource` / `fetchEventSource`. The span wrapping is unchanged — streaming is a view
over the same run, still persisted and visible in `/traces`.

## UI — Next.js + React + Tailwind, primary journey only
The harness builds a UI **by default**; **headless products skip it** (set in `spec/tech-stack.md` — an
API/cron/Slack-only agent ships no web UI). When built, scope it to the **primary journey** the user
described in `spec/product.md` — *not* a screen per capability. Usually one page: enter a goal → see the
answer stream in → a link to its trace. The agent's value is the run, not the chrome.

- **Stack:** Next.js (App Router) + React + Tailwind. The page calls `POST /runs` (or `/runs/stream` for
  SSE) and renders the `ok()` envelope. Keep state minimal — input, streaming answer, run-id link.
- **Always render the answer as markdown.** LLM output *is* markdown — headings, tables, lists, code,
  bold. Render it through a markdown component (`react-markdown` + `remark-gfm` for tables/strikethrough),
  never as raw text or `{answer}` in a `<pre>`. Stream tokens into that same markdown surface so the
  formatted answer builds up live. A wall of unformatted text is a bug, not a style choice.
- **Honesty:** real network call to the real agent. No mocked answer, no fake latency, no lorem.
- **Deep-link the trace:** show `run_id` as a link to `/traces` so a human can inspect the actual steps —
  the UI and the observability layer are the same truth (`patterns/observability-and-evals.md`).
- **Don't rebuild `/traces`.** The server already renders the timeline; the UI links to it.
- **One command runs both.** Ship a `make dev` that starts backend **and** UI together
  (`trap 'kill 0' INT; python -m agent & cd ui && npm run dev`) — Ctrl-C kills both. The user never starts the
  backend by hand; a UI with a dead backend is the most common "it's broken" report.
- **Send a `session_id` whenever you send `data`.** A resource POSTed without a `session_id` is loaded into a
  server-minted session (the recipe never drops the upload), but that session id is internal — generate one
  client-side (`crypto.randomUUID()`, as in the `page.tsx` recipe) and send it WITH the first `data` POST so
  the follow-up turn can reuse the same session. Omitting it on Q1 means Q2 can't find Q1's resource.
- **Persist the session client-side.** For multi-turn UIs, store `thread_id` (and the active resource id) in
  `localStorage` so a page reload resumes the same conversation — React state alone resets to a fresh thread
  on every refresh, which reads to the user as "all my history vanished."
- **Show cost where the user works.** Surface per-run tokens + cost in the product UI, not only at `/traces`,
  and keep a running session total visible. Cost you can't see is cost you discover too late.

### Visualizations — suggest minimal, let the user drive (data / analytics products only)
Skip this entirely for non-data products. When the product *does* produce charts, do **not** auto-render a
wall of dashboards the user never asked for — that pre-judges what matters and buries the answer in noise.
Charts are an **affordance, not the default surface**: the primary journey stays ask → answer, and
visualization is opt-in and user-driven.
- **Suggest, don't flood.** Offer a few sensible default charts inferred from the schema (one per key
  column or relationship) as one-click suggestions — not a pre-built board of everything.
- **User-authored charts.** The user adds a chart by typing a natural-language prompt ("revenue by region
  as a bar chart"); the agent returns the chart spec (Plotly JSON via the `finish` tool —
  `patterns/react-agent.md`) and the UI renders it. The chart comes from a real run, not a hardcoded view.
- **Fine-tune by prompt.** Each chart keeps its prompt editable — the user refines the wording and the
  chart regenerates. A chart is a conversation, not a frozen artifact.

**Verify the UI serves before reporting done.** Confirm HTTP 200 from the dev server before running
the gate. If it returns an error, read the process log — the first error line names the cause.
Common fixes: wrong dev port (default **3001**, not 3000 — conflicts with Grafana and other local
tools), a browser-only library evaluated server-side (disable SSR for that component), or a missing
global that the Node.js version partially implements. Fix the root cause from the log; don't guess.

### UI prerequisites — scaffold the ui/ project + the browser binary, or check 7 dies undiagnosably
A UI page with no runnable project and a Playwright step with no browser are both opaque to a non-tech user
(`Executable doesn't exist` / `next: command not found`). Before the gate's check 7 the build MUST:

1. **Scaffold a minimal but runnable `ui/` Next.js project** — at least `ui/package.json`, `ui/next.config.mjs`,
   `ui/app/layout.tsx`, `ui/app/page.tsx`. A copyable `package.json` (pin current majors when you generate):
   ```jsonc
   {
     "name": "agent-ui", "private": true,
     "scripts": { "dev": "next dev -p 3001", "build": "next build", "start": "next start -p 3001" },
     "dependencies": { "next": "^15", "react": "^19", "react-dom": "^19",
                       "react-markdown": "^9", "remark-gfm": "^4" }
   }
   ```
   Port **3001** (not 3000 — `next dev -p 3001`). `make dev` runs `cd ui && npm run dev` against this project.

   **`ui/app/page.tsx` MUST expose the exact accessible names the e2e journey binds to.** Playwright's
   `get_by_role(name=…)` matches the element's *accessible name* (a `<label>`, `aria-label`, or `placeholder`)
   — a freehand page with a "Paste your diff" label, a "Submit" button, or `data-testid="result"` will make
   check 7 die with an opaque Playwright `TimeoutError` a non-tech owner can't diagnose. This is the UI-tier
   analogue of the `GOAL`/`CRITERION` sync rule: **the page and the e2e journey share one contract — keep the
   accessible names in sync.** The journey (§ Gate) locates: a `name="goal"` textbox, a `name="<resource>"`
   textbox for a session-scoped build (e.g. `contract`/`diff`), a `Run` button, a `data-testid="answer"`
   markdown surface, and a `trace` link. A copyable minimal page that ships exactly those:
   ```tsx
   // ui/app/page.tsx — the accessible names below are the e2e contract; do not rename without updating the journey.
   "use client";
   import { useState } from "react";
   import ReactMarkdown from "react-markdown";
   import remarkGfm from "remark-gfm";
   export default function Page() {
     const [resource, setResource] = useState("");   // session-scoped builds only; delete for a key-free agent
     const [goal, setGoal] = useState("");
     const [answer, setAnswer] = useState("");
     const [runId, setRunId] = useState("");
     async function run() {
       const sid = crypto.randomUUID();
       const body: any = { goal, session_id: sid };
       if (resource) body.data = resource;            // DATA-INGEST: send the resource WITH a session_id (server.py)
       const res = await fetch("http://localhost:8001/runs", {
         method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
       });
       const json = await res.json();
       setAnswer(json.data?.answer ?? json.error?.message ?? "");
       setRunId(json.data?.run_id ?? "");
     }
     return (
       <main style={{ maxWidth: 720, margin: "2rem auto", fontFamily: "system-ui" }}>
         {/* session-scoped builds only — the aria-label IS the accessible name the journey fills */}
         <textarea aria-label="contract" placeholder="Paste the document"
                   value={resource} onChange={(e) => setResource(e.target.value)} rows={6} style={{ width: "100%" }} />
         <input aria-label="goal" placeholder="Ask a question"
                value={goal} onChange={(e) => setGoal(e.target.value)} style={{ width: "100%" }} />
         <button onClick={run}>Run</button>
         <div data-testid="answer"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown></div>
         {runId && <a href={`http://localhost:8001/traces`}>trace</a>}
       </main>
     );
   }
   ```
   For a session-scoped build the `aria-label="contract"` textbox carries the resource and is sent as `data`
   with a `session_id` (rename `contract`→`diff`/`document` to match your journey + fixture). For a key-free
   agent delete the resource textarea and the `data` field. Keep `aria-label="goal"`, the `Run` button text,
   `data-testid="answer"`, and the `trace` link verbatim — the journey (§ Gate) binds to all four.
2. **Install deps + the chromium binary**: `cd ui && npm install`, then `uv run playwright install chromium`
   (the browser the `page` fixture drives — never auto-downloaded). Put both in a `make setup` / install step,
   never inside the gate. The gate **auto-skips check 7 with a printed reason** when `ui/node_modules` is
   absent (`workflows/gates.md`), so a headless or un-scaffolded build fails on a real defect, not on a
   missing browser.

A headless product (`spec/tech-stack.md` UI = none) skips all of this and runs the API + outcome-eval gate only.

### Gate — Playwright asserts the post-JS DOM (run it, don't trust it)
The journey test drives a real browser against the running app and asserts what a user actually sees
*after* React hydrates and the answer arrives — never the raw HTML, never a 200 alone. → `workflows/gates.md`.
```python
# tests/e2e/test_primary_journey.py  (pytest + playwright; agent server + next dev both up)
import pathlib, pytest
# Skip cleanly if pytest-playwright isn't installed, rather than aborting COLLECTION of the whole suite.
# Gate check 2 is `uv run pytest` over EVERYTHING, including tests/e2e/; a bare `from playwright…` import on
# a project where the package isn't present raises at collection time and `pytest` exits non-zero before any
# other test even registers (`Interrupted: 1 error during collection`). importorskip turns that into a clean
# SKIP. pytest-playwright IS pinned in pyproject.toml for a UI build (build.md §3 / tech-stack.md), so this
# guard only ever fires on a headless project that shipped the file by mistake — never on a real UI build.
pytest.importorskip("playwright")
from playwright.sync_api import expect

def test_user_gets_an_answer(page):
    page.goto("http://localhost:3001")
    # DATA-INGEST branch (REQUIRED when spec/agent.md marks session-scoped resources ON — C-SESSION-SCOPE):
    # an "analyze an uploaded X" agent's first question must CARRY the resource, exactly like demo_gate.sh's
    # Q1 `data` field (workflows/gates.md check 5). Skip it and Q1 hits an empty session: the agent answers
    # "No <resource> is loaded for this session" — a NON-EMPTY string, so not_to_be_empty() PASSES and the UI
    # gate goes GREEN on a wrong-answer journey (the 200-with-wrong-answer class this gate exists to catch,
    # leaking through the browser tier where the outcome judge never reaches — HARDENING-LOG iter 7). So the
    # journey MUST first paste/upload the fixture, then assert the answer contains a REAL fixture value, not
    # merely non-empty. For a key-free/own-data agent (no C-SESSION-SCOPE) delete this branch.
    fixture = pathlib.Path("scripts/fixtures/contract.txt").read_text()   # build.md §3 fixture
    page.get_by_role("textbox", name="contract").fill(fixture)           # the upload affordance the UI must ship
    page.get_by_role("textbox", name="goal").fill("How long is the termination notice period?")
    page.get_by_role("button", name="Run").click()
    answer = page.get_by_test_id("answer")
    expect(answer).not_to_be_empty(timeout=30_000)        # post-JS DOM, after the real run completes
    expect(answer).to_contain_text("30 days")             # a REAL fixture value — not merely non-empty
    expect(page.get_by_role("link", name="trace")).to_be_visible()   # deep-link to /traces present
```
The recipe above shows the **data-ingest** journey (a session-scoped agent). For a non-ingest agent the goal
field alone carries the question and the `to_contain_text` assert checks a known answer substring (not just
`not_to_be_empty`, which a "no data loaded" error would also satisfy). The non-negotiable in **both** shapes:
assert the answer contains a REAL expected value, never merely that it is non-empty — a non-empty string is
also what a wrong-answer error returns, so `not_to_be_empty()` alone lets a wrong-answer journey pass the UI
gate (HARDENING-LOG iter 7).

**"A real expected value" means a value derivable deterministically from the INPUT — not a paraphrase of the
output.** For an **extraction** agent the answer echoes a literal token from the resource (the `"30 days"`
example), so asserting that token is robust. But for the large **transform/judgment** class — code review,
summarize, classify, verdict — the answer is *generated prose that paraphrases the input*, and there is no
guaranteed literal substring the live model will emit. Do **not** over-fit to a brittle paraphrase substring
(it false-REDs the moment the model words it differently) and do **not** fall back to `not_to_be_empty()`
(the false-green this rule forbids). Instead assert the answer echoes a literal **symbol present in the
input** — an identifier, a number, a filename — which the model reliably reproduces when it actually engaged
with the input. For a code-review-on-a-diff agent, assert the review mentions a changed identifier from the
diff (`get_user`, `login`, a SQL keyword) rather than a paraphrase of the critique. (Alternatively, run a
cheap-tier outcome-judge assertion in the e2e tier too.) Input-symbol echo is the robust default for any
non-extraction agent.

A headless product replaces this with the API + outcome-eval gate only (no browser). The mechanical
two-tier success (demo / productionise) is defined in `harness/harness.md` and `workflows/gates.md` — this
recipe just wires the serving edge into it.
