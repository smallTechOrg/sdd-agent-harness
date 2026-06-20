# Usage-spec: fastapi (+ uvicorn)

**Version: `fastapi` 0.11x · `uvicorn` 0.3x** (verify latest before pinning — a bump REFRESHES this file)
**Stamped: 2026-06**

Guards: `interface.md` (`agent/server.py`, `agent/__main__.py`) — `/health`, `POST /runs`, `/traces`, SSE.

## App + lifespan (the boot contract the core relies on)
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_required_config()    # fail LOUD at boot if required config missing (config.py) — BEFORE init_db
    await init_db()               # create_all — sqlite local-first
    yield                         # (teardown after yield if needed)

app = FastAPI(title="agent", lifespan=lifespan)
```
- ✅ Use the **`lifespan=` async-context-manager** pattern. ❌ Do NOT use `@app.on_event("startup")` /
  `@app.on_event("shutdown")` — deprecated; the lifespan CM is the current API.
- ✅ `validate_required_config()` runs **before** `init_db()` so a missing key fails the boot with a named
  error, not a mid-run 500 (`C-PORT`/`C-ENVELOPE` neighbours; `model-and-providers.md` RULE 2).

## The JSON envelope — every route returns `ok(data)` or raises `ApiError` (`C-ENVELOPE`)
```python
from fastapi.responses import JSONResponse

def ok(data): return {"ok": True, "data": data}

class ApiError(Exception):
    def __init__(self, code, msg="", status=500): self.code, self.msg, self.status = code, msg or code, status
def api_error(code, msg="", status=500): return ApiError(code, msg, status)

@app.exception_handler(ApiError)
async def _h(_req, exc: ApiError):
    return JSONResponse({"ok": False, "error": {"code": exc.code, "message": exc.msg}}, status_code=exc.status)
```
- ❌ Never return an HTML error page or let a bare 500 stacktrace reach the client — wrap unexpected
  exceptions as `api_error("RUN_FAILED", str(e), status=500)`.

## Request body — a pydantic model, not raw dict
```python
from fastapi import Request
from pydantic import BaseModel
class RunIn(BaseModel): goal: str

@app.post("/runs")
async def create_run(request: Request, body: RunIn):
    # The checkpointer is created in the LIFESPAN and stashed on app.state. Read it with getattr(..., None),
    # NOT `request.app.state.checkpointer` — httpx's ASGITransport (the keyless contract test) skips the
    # lifespan, so a bare access raises AttributeError. See the authoritative handler in `interface.md`
    # (this is the same shape, minus the session/data seam) and the ASGITransport note below.
    checkpointer = getattr(request.app.state, "checkpointer", None)
    return ok(await run_agent(body.goal, checkpointer=checkpointer))
```
- ✅ Async route handlers (`async def`) — our stack is async; a sync handler blocks the event loop on the
  DB/LLM await.
- ⚠️ This is the **stripped** shape; the **authoritative** `POST /runs` (with the `session_id`/`data` seam and
  the full envelope) is `interface.md` § *Code — `agent/server.py`*. Keep this in sync with it — never diverge.

## SSE streaming (when `Streaming: yes` in the spec)
```python
from fastapi.responses import StreamingResponse

async def _events():
    async for tok in stream_tokens(goal):
        yield f"data: {json.dumps({'token': tok})}\n\n"
    yield f"data: {json.dumps({'done': True, 'answer': ..., 'run_id': ..., 'thread_id': ...})}\n\n"

@app.get("/runs/stream")
async def stream(goal: str):
    return StreamingResponse(_events(), media_type="text/event-stream")
```
- ✅ `media_type="text/event-stream"`, each event `data: <json>\n\n` (blank-line terminated).
- ✅ The final `done` event MUST carry every field the UI consumes (answer, run_id, thread_id, + any
  structured payload like a `chart_spec`) — a dropped field is the canonical silent-UI-blank bug.

## Run it — `python -m agent` (`C-PORT`: port 8001)
```python
# agent/__main__.py
import uvicorn
from .config import get_settings
uvicorn.run("agent.server:app", host="0.0.0.0", port=get_settings().port)   # default 8001, NOT 8000
```
- ✅ Pass the app as an **import string** (`"agent.server:app"`) so reload works; bind the configured port.
- For the gate over HTTP use a real `httpx` + `ASGITransport` client in tests (no network) and `python -m agent`
  for the live boot (`gates.md` DEMO 2). **`ASGITransport` does NOT run the FastAPI lifespan** — anything set on
  `app.state` in the lifespan (the `checkpointer`) is therefore **absent** in-process, so any handler that reads
  it must use `getattr(request.app.state, "checkpointer", None)` (above), never a bare attribute access, or every
  in-process contract test 500s with `'State' object has no attribute 'checkpointer'` (HARDENING-LOG iter 9). If
  a test genuinely needs the lifespan to run (e.g. to assert init_db ran), wrap the app in
  `asgi-lifespan`'s `LifespanManager` (`async with LifespanManager(app): …`) and pin `asgi-lifespan`.
