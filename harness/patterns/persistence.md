# Pattern: Persistence (Layer — the data spine)

Every run, message, and span lands here. **Generate fresh at build time**, pinning the *current*
`sqlalchemy`, `aiosqlite`, and (for prod) `asyncpg` — verify latest before pinning, a guessed version 404s.
The code below is proven working; use it verbatim.

## The one rule: SQLite local → Postgres prod, same code, swap only the URL
Async SQLAlchemy 2.0 abstracts the backend. You change a **driver/URL**, never a query.

| Rung | `APP_DATABASE_URL` | Driver | When |
|------|--------------------|--------|------|
| **Local-first** | `sqlite+aiosqlite:///./agent.db` | `aiosqlite` | dev, the demo gate, tests |
| **Prod** | `postgresql+asyncpg://user:pw@host/db` | `asyncpg` | `/deploy`, before any deploy gate |

**NEVER `psycopg2`** (sync) — it blocks the event loop and every recipe in this repo assumes async I/O.
Postgres uses `asyncpg`, full stop. The deploy gate runs the *same tests* against the Postgres rung
(`workflows/gates.md`) — that's the whole point of one code path.

## Code — `agent/db.py` (proven, verbatim)
```python
import datetime as dt
import uuid
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .config import get_settings


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"
    id:         Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    goal:       Mapped[str]  = mapped_column(Text)
    status:     Mapped[str]  = mapped_column(String, default="running")   # running|completed|error
    answer:     Mapped[str | None] = mapped_column(Text, nullable=True)
    iterations: Mapped[int]  = mapped_column(Integer, default=0)
    input_tokens:  Mapped[int]   = mapped_column(Integer, default=0)      # summed from this run's LLM spans
    output_tokens: Mapped[int]   = mapped_column(Integer, default=0)
    cost_usd:      Mapped[float] = mapped_column(Float, default=0.0)       # tokens × per-1M price (config.py)
    thread_id:     Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # multi-turn session
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"
    id:         Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    run_id:     Mapped[str]  = mapped_column(ForeignKey("runs.id"), index=True)
    role:       Mapped[str]  = mapped_column(String)                      # system|human|ai|tool
    content:    Mapped[str]  = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Span(Base):
    __tablename__ = "spans"
    id:          Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    run_id:      Mapped[str]  = mapped_column(ForeignKey("runs.id"), index=True)
    name:        Mapped[str]  = mapped_column(String)                     # OTel GenAI: invoke_agent|chat <model>|execute_tool.<name>
    kind:        Mapped[str]  = mapped_column(String, default="INTERNAL") # INTERNAL|LLM|TOOL
    attributes:  Mapped[dict] = mapped_column(JSON, default=dict)
    start_ms:    Mapped[float] = mapped_column(Float)
    end_ms:      Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[float] = mapped_column(Float)
    created_at:  Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


engine = create_async_engine(get_settings().database_url)
_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


def get_sessionmaker() -> async_sessionmaker:
    """The one session accessor. Callers do: `async with get_sessionmaker()() as s: ...; await s.commit()`."""
    return _sessionmaker


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

`expire_on_commit=False` so objects stay usable after `commit()` (you read `.answer` post-write without a
reload). `get_sessionmaker()` returns the `async_sessionmaker`; every recipe opens a session with
`async with get_sessionmaker()() as s:` and commits explicitly. `init_db()` is wired into the FastAPI
lifespan (`agent/server.py`) so tables exist on boot. `db.py` exports `get_sessionmaker` and `init_db`.

## The three core tables — the agent's flight recorder
- **`runs`** — one row per `POST /runs`. The unit of work: goal in, answer + status + iteration count out.
- **`messages`** — the full transcript (system/human/ai/tool), keyed to a run. Persisted by `agent/runner.py`
  after the graph finishes.
- **`spans`** — one row per LLM call and tool execution, OTel-GenAI-shaped, written by the `span()` context
  manager (`patterns/observability-and-evals.md`). The built-in `/traces` viewer reads straight from this table.

These three are non-negotiable: they *are* observability + evals. Don't skip `spans` to "add it later" —
the demo gate requires visible traces.

**Cost is a first-class column, not an afterthought.** Every run consumes tokens and money, so `runs` carries
`input_tokens` / `output_tokens` / `cost_usd` from Phase 1 — sum the run's `LLM` spans' `usage_metadata`,
price via per-1M rates in `agent/config.py`. Wiring this in later means a migration *and* a UI retrofit; from
the start it's free. For **multi-turn** products add a `threads` (session) table keyed by `thread_id` that
accumulates per-session token + cost totals and the active resource id — that row is what the UI's
always-visible session header reads (`patterns/interface.md`).

## Session-scoped resources — key by `session_id`, persist across turns, release only on delete
A parsed file, a loaded DataFrame, a built index, **a pasted document or transcript** — anything that is
**loaded once and reused across follow-up turns**, regardless of size or cost — is a *session* resource, not
a *per-question* one. (Don't gate on "heavy" / "expensive to derive": a meeting transcript is just a cheap
string, yet a Q2 like "now group those action items by owner" still needs it without a re-paste. The trigger
is **reuse across turns**, not cost.) Key it by `session_id` (= `thread_id`) and keep it for the life of the
session.

**The discriminator — supplied vs generated (read before reaching for this).** sessions.py exists for a
resource that **ARRIVES from the user**: uploaded or pasted via the `data` field, parsed by `load_resource`,
then reused. A resource the **model GENERATES on Q1 and then REFINES on Q2** — an itinerary, a draft email, a
story, a project plan, the whole *generate-then-refine* class — is **not** a session resource: it is carried
across turns by **short-term memory** (the checkpointer transcript + the `runner.py` prior-message merge —
`patterns/memory.md`, `patterns/react-agent.md`). It needs **no sessions.py**, no `load_resource`, no `data`
field, no `current_session_id` read tool. Generating that machinery for a generated-then-refined resource is
a bug: there is **nothing to populate it** (the user uploads nothing), so you ship dead code, or a read tool
that always reports "no data loaded." Rule of thumb: *user uploads/pastes it → sessions.py; the model writes
it → checkpointer transcript, no sessions.py.* Example: "plan a 3-day Lisbon itinerary" (Q1) then "make day 2
rainy-day-friendly" (Q2) carries the itinerary in the transcript — no sessions.py; "analyze this CSV" (Q1,
`data` carries the file) then "now break it down by region" (Q2) keeps the DataFrame in sessions.py.

**Releasing it after each question is a correctness bug**: Q2 ("now break that down by region")
arrives, the DataFrame is gone, and the agent answers `SESSION_DATA_LOST` instead of the follow-up — a green
build, a broken product, the single most common multi-turn failure.

A small in-process store does it (the resource is live objects, not rows — the DB row records *that* a
session has one + its metadata, the store holds the object). It also exports the **`current_session_id`
ContextVar** that lets a tool find the active session without the model supplying it (see the read path below):
```python
# agent/sessions.py — session-scoped live resources, keyed by session_id, released ONLY on delete
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

# Set by agent/runner.py around graph.ainvoke (patterns/react-agent.md / interface.md) so a @tool can read the
# active session WITHOUT exposing session_id as a model-supplied argument. A tool does `current_session_id.get()`.
current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)

@dataclass
class SessionResources:
    by_id: dict[str, Any] = field(default_factory=dict)   # resource_id -> live object (DataFrame, index, …)

_SESSIONS: dict[str, SessionResources] = {}

def get_session(session_id: str) -> SessionResources:
    """Return (creating if absent) the resource bag for a session. Survives every turn on that session."""
    return _SESSIONS.setdefault(session_id, SessionResources())

def release_session(session_id: str) -> None:
    """Drop a session's resources — call ONLY on explicit session delete, NEVER per question."""
    _SESSIONS.pop(session_id, None)
```

### The HTTP ingest seam — how the resource actually gets IN (the missing populate path)
The store above describes *holding* a resource; this is how a resource *arrives over HTTP* for an "analyze
an uploaded X" agent. `POST /runs` carries an optional `data` field (`patterns/interface.md` RunIn); on a
turn that has it, the server calls `load_resource(session_id, data)` **before** the run, so the run's tools
see it and **Q2 on the same session reuses it** (no re-upload). Without this populate path the demo gate's
Q1 hits an empty session and the agent answers "no data is loaded" — a 200 that the outcome eval fails.
Generate `load_resource` only for a data-ingesting capability (`C-SESSION-SCOPE`); key-free/own-data agents
omit it. The parse is domain-specific — a CSV example, parsed once and reused every turn:
```python
# agent/sessions.py (cont.) — populate the session store from an uploaded blob, parsed ONCE
import io
import pandas as pd                                   # pin current pandas in pyproject.toml

def load_resource(session_id: str, data: str, resource_id: str = "main") -> str:
    """Parse an uploaded blob ONCE and stash the live object in the session bag (survives every turn).
    Idempotent per turn: if the agent re-POSTs the same data on a follow-up it just refreshes the object,
    it does NOT release prior resources (release happens only on explicit session delete)."""
    df = pd.read_csv(io.StringIO(data))               # domain parse — swap for your resource type
    get_session(session_id).by_id[resource_id] = df
    return resource_id
```
### The read path — how a tool finds the session WITHOUT the model supplying it (the missing piece)
The query tool reads the resource back **by the active session**, never re-parses. The session is NOT a tool
argument: a `@tool def query_dataframe(session_id: str)` would expose `session_id` as a model-visible field the
LLM has to hallucinate (it doesn't know the thread id), and a parameterless tool has no other way to learn it.
The loop does **not** inject run/session context — `patterns/react-agent.md`'s `tools_node` calls each tool
with *only* `tc["args"]` (the model-supplied arguments). So the tool reads the **`current_session_id`
ContextVar** that `agent/runner.py` sets around `graph.ainvoke` (and `agent/sessions.py` exports, above):
```python
# in agent/tools.py — the query tool takes ONLY domain args; the session comes from the ContextVar
from langchain_core.tools import tool
from .sessions import current_session_id, get_session

@tool
def query_dataframe(question: str) -> str:                # NOTE: no session_id parameter — model never sees it
    """Answer a question about the loaded spreadsheet/transcript for THIS session."""
    sid = current_session_id.get()
    df = get_session(sid).by_id.get("main") if sid else None
    if df is None:
        return "No spreadsheet is loaded"                 # truly absent — not a hallucinated-id miss
    ...                                                    # run the domain query against df
```
The runner sets the ContextVar so any tool in the run sees the right session (one line in `runner.py`,
`patterns/interface.md` § *Code — `agent/runner.py`*):
```python
from .sessions import current_session_id
token = current_session_id.set(session_id)
try:
    result = await graph.ainvoke(state, config=config)
finally:
    current_session_id.reset(token)
```
For binary/large uploads expose a sibling `POST /sessions/{id}/resource` (multipart) that calls the identical
`load_resource`.

Rules: load on first use, look up by `session_id` on every later turn, **release only** from an explicit
`DELETE /sessions/{id}` (or a TTL sweep) — never at the end of a run. For a multi-process deploy, back the
same interface with Redis/disk so the resource survives the worker that loaded it; the *contract* (key by
session, release on delete) is identical. The `threads` row (below) records the active resource id so a
reconnecting UI knows what's loaded.

## The JSON envelope — `ok()` / `api_error()`, never an error page
Every route returns one shape, so the UI parses one contract and a non-tech user never hits a raw stacktrace
or an `error.html`. On success: `ok(data)`. On failure: read `state["error"]`, log it **with the `run_id`**,
and raise/return `api_error("RUN_FAILED", status=500)` — a coded, JSON error the UI renders as a friendly
message with the run id to deep-link into `/traces`. The envelope helpers live in `agent/server.py`
(`patterns/interface.md`); persistence's part is that a failed run writes `status="error"` + the reason so
`/traces` and the envelope tell the same story.

## Adding domain entities — extend, don't fork
Your capability's nouns (tickets, invoices, documents, …) are new models on the **same `Base`**. Same engine,
same session, same SQLite→Postgres ladder — `init_db()` creates them automatically.

```python
# agent/domain.py — domain entities live alongside the core tables
import datetime as dt
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, _now, _uuid   # reuse the same declarative Base + helpers — do NOT define a second Base

class Ticket(Base):                 # example: a support agent's domain noun
    __tablename__ = "tickets"
    id:         Mapped[str]  = mapped_column(String, primary_key=True, default=_uuid)
    run_id:     Mapped[str]  = mapped_column(ForeignKey("runs.id"), index=True)  # tie domain rows to the run
    subject:    Mapped[str]  = mapped_column(String)
    body:       Mapped[str]  = mapped_column(Text)
    status:     Mapped[str]  = mapped_column(String, default="open")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

Rules: **one `Base`** (a second one means tables your `init_db()` never creates); reference `runs.id` so
domain data joins back to the run that produced it; index your foreign keys. Tools that write domain rows are
plain in-process `@tool`s using the same `get_sessionmaker()` (`patterns/tools-and-mcp.md`).

### Writing rows — the session pattern
```python
from .db import get_sessionmaker
from .domain import Ticket

async def open_ticket(run_id: str, subject: str, body: str) -> str:
    async with get_sessionmaker()() as session:
        t = Ticket(run_id=run_id, subject=subject, body=body)
        session.add(t)
        await session.commit()      # async all the way down — never a sync driver
        return t.id
```

Beyond `commit()`: stays async end-to-end, so it never blocks the loop. For long writes, hand off with
`asyncio.create_task` and return the turn immediately (the async-write rule in `patterns/memory.md`).

## Migrations — when the schema outgrows `create_all`
`init_db()`'s `create_all` makes *new* tables but never *alters* existing ones. The moment a deployed
Postgres DB has data you can't drop, add **Alembic** (pin current): `alembic init`, point `sqlalchemy.url` at
`APP_DATABASE_URL`, autogenerate against the same `Base.metadata`. Local SQLite dev keeps using `create_all`;
prod runs migrations. This earns its place at `/deploy`, not before.

## Tests use the SAME driver as prod (conftest, proven pattern)
Tests must not invent a special path — they exercise the real async engine, just against a throwaway DB. Set
`APP_DATABASE_URL` before importing `agent.db` (the engine is built at import time), and create/drop tables
per test for isolation.

```python
# tests/conftest.py
import os
os.environ["APP_DATABASE_URL"] = "sqlite+aiosqlite:///./test_agent.db"   # set BEFORE importing agent.db
import pytest_asyncio
from agent.db import Base, engine

@pytest_asyncio.fixture(autouse=True)
async def _fresh_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```
This autouse fixture is `async` — it only runs if the generated `pyproject.toml` sets
`[tool.pytest.ini_options] asyncio_mode = "auto"` (`workflows/build.md` §3). Under pytest-asyncio's default
strict mode it is silently skipped, so every test runs against an un-migrated DB. The `asyncio_mode = "auto"`
line is mandatory.

The local demo gate runs these on SQLite. The **deploy gate runs the identical suite with
`APP_DATABASE_URL` pointed at a real Postgres+`asyncpg`** — same models, same code path, proving the URL
swap before any deploy. A green SQLite suite is necessary, not sufficient. → `workflows/gates.md`.

## Spec wiring
`spec/tech-stack.md` sets the DB rung (SQLite local default → Postgres deploy target) and declares domain
entities the capability needs. `spec/capabilities/*.md` EARS criteria name the rows a run must produce — the
outcome eval reads them back from these tables to grade the run.
