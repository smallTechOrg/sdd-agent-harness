# Pattern: Memory (Layer 3)

Three concentric scopes. **Generate fresh at build time**, pinning the *current* `langgraph`,
`sqlalchemy`, `sqlite-vec` / `pgvector` (verify latest first — a guessed version 404s). Most agents need
only the inner two; the outer one **earns its place** when a real capability requires recall across runs.

| Scope | Lives where | Lifetime | When |
|-------|-------------|----------|------|
| **Working** | graph `AgentState` (`patterns/react-agent.md`) | one run | always — it *is* the loop |
| **Short-term** | session store keyed by `thread_id` | a session/thread | multi-turn conversation |
| **Long-term** | external store, vector-indexed | forever | recall across runs/users |

## Working memory — already done
The message list in `AgentState` (`messages`, `iterations`, `answer`, `run_id`) is working memory. Nothing
to add. Sub-agents get *isolated* working memory (their own state) and return only a summary — that
context-isolation is the Deep-Agent pillar in `patterns/react-agent.md`, not a new store.

## Short-term memory — a checkpointer
Don't hand-roll session state. LangGraph's checkpointer persists `AgentState` per `thread_id`, so a second
turn resumes with full history. Same SQLite-then-Postgres ladder as the rest of the app (`agent/db.py`).

```python
# agent/memory/short_term.py — the checkpointer is passed INTO build_graph (it owns the one .compile()).
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver      # pip: langgraph-checkpoint-sqlite
# prod: from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  (asyncpg DSN — NEVER psycopg2)

# In the server lifespan, open ONCE and keep on app.state (patterns/interface.md server.py):
#   cm = AsyncSqliteSaver.from_conn_string("checkpoints.db")
#   app.state.checkpointer = await cm.__aenter__()
# build_graph takes it as a parameter — DO NOT call .compile() on build_graph's result (that double-compiles):
#   graph = build_graph(model, checkpointer=cp)          # NOT build_graph(model).compile(checkpointer=cp)
# Then invoke with a thread (runner.py also reloads prior messages — see below):
#   await graph.ainvoke(state, config={"configurable": {"thread_id": session_id}, "recursion_limit": 50})
```
The thread is the session. Resuming the same `thread_id` keeps the transcript in the checkpoint — but note
the `AgentState` has **no `add_messages` reducer** (`patterns/react-agent.md` WARNING), so the freshly-seeded
`messages` would *overwrite* the replay. The **runner owns the merge**: on a follow-up turn it reads
`cp["channel_values"]["messages"]` out of the checkpoint, strips the stale `SystemMessage`, and prepends them
to a fresh system prompt + the new goal (`patterns/interface.md` `run_agent`). The plain-list rule and the
checkpointer coexist exactly this way. Surface `thread_id` on `POST /runs` so a client can continue a
conversation.

## Long-term memory — the 3-type external store
One store, three record types (the namespace tells them apart). Earns its place beyond working/short-term.

- **Episodic** — *what happened*: past runs/outcomes/user events, for few-shot recall ("last time, X worked").
- **Semantic** — *facts*: durable knowledge & user preferences ("user is on the EU plan").
- **Procedural** — *how-to*: learned instructions/skills the agent reuses (a distilled playbook).

Retrieval here is the same embed-and-search machinery as document RAG — share the vector layer, don't fork
it; see `patterns/retrieval.md`. Memory differs only in *what* you store and *when you write*.

### Schema — extends `agent/db.py`
Add to the existing async-SQLAlchemy models (`runs`, `messages`, `spans`). Local-first SQLite + `sqlite-vec`;
the column type is the only thing that changes on the Postgres+`pgvector` rung.

```python
# agent/memory/models.py
import datetime as dt
from sqlalchemy import String, Text, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from agent.db import Base   # same declarative Base as runs/messages/spans

class Memory(Base):
    __tablename__ = "memories"
    id:         Mapped[str]  = mapped_column(String, primary_key=True)        # uuid4
    namespace:  Mapped[str]  = mapped_column(String, index=True)              # "<user>:episodic" | ":semantic" | ":procedural"
    kind:       Mapped[str]  = mapped_column(String, index=True)              # episodic | semantic | procedural
    content:    Mapped[str]  = mapped_column(Text)                            # the text we embed + return
    meta:       Mapped[dict] = mapped_column(JSON, default=dict)              # tags for metadata filtering
    score:      Mapped[float]= mapped_column(Float, default=1.0)              # decays/boosts; reranker input
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC),
                                                    onupdate=lambda: dt.datetime.now(dt.UTC))
# Embeddings: a sqlite-vec virtual table `vec_memories(memory_id, embedding float[N])`
# (prod: a `vector(N)` column + an ivfflat/hnsw index under pgvector). Reuse the embedder from patterns/retrieval.md.
```

### Six table-stakes capabilities (a store missing any of these is a toy)
1. **Async writes** — never block the agent loop on a write. `await session.commit()`, or hand the write to
   a background task (`asyncio.create_task`) so the turn returns immediately. All I/O is async (no psycopg2).
2. **Reranking** — vector top-k is recall, not precision. Pull `k*4` candidates, then rerank (a cross-encoder
   or `score`/recency blend) down to `k`. Same reranker as `patterns/retrieval.md`.
3. **Metadata filtering** — filter on `meta`/`namespace`/`kind` *before* similarity, so a search scopes to one
   user, one type, one tag — not the whole table.
4. **Accurate timestamps** — timezone-aware UTC (`datetime.now(dt.UTC)`), persisted; `updated_at` on write.
   Recall and decay are wrong without them. The `/traces` viewer already shows these for spans.
5. **Configurable depth** — `recall(k=...)` and a write threshold are settings (`agent/config.py`, prefix
   `APP_`), not hard-coded. Cheap runtime tier ⇒ keep injected context tight.
6. **Structured errors** — recall failure returns an empty list + a logged error span, never crashes the run.
   A degraded memory is recoverable; a 500 is not.

### Tools the agent calls
Plain typed in-process `@tool`s (internal capability ⇒ no MCP — see `patterns/tools-and-mcp.md`). Wrap each
in a `span` so reads/writes show in `/traces` (`patterns/observability-and-evals.md`).

```python
# agent/memory/tools.py
from langchain_core.tools import tool

@tool
async def remember(content: str, kind: str = "semantic", tags: dict | None = None) -> str:
    """Persist a durable fact (semantic), event (episodic), or how-to (procedural) for future runs."""
    # embed(content) -> upsert Memory + vec row in a span; async commit; return the new id.

@tool
async def recall(query: str, kind: str | None = None, k: int = 5) -> list[dict]:
    """Search long-term memory; filter by kind/tags first, vector-search, rerank, return top-k. Never raises."""
    # metadata-filter -> vector top (k*4) -> rerank -> [:k]; on error log span + return [].
```
Inject the top recalls into the system prompt at run start (`agent/runner.py`) so they ride along as
context; let the model also call `recall` mid-loop for targeted lookups.

## Spec wiring
`spec/agent.md` turns long-term memory on; `spec/tech-stack.md` picks the embedder + vector backend (SQLite
+ `sqlite-vec` local, Postgres + `pgvector` prod). Working + short-term are on by default once a capability
needs multi-turn.

## Gate (run it — don't trust it)
Drive with the `FakeModel` (no API key, `patterns/react-agent.md`); a fake/deterministic embedder for vectors.
- `remember` then `recall(same query)` returns the item; an off-topic query (with `kind` filter) excludes it.
- A forced embed/DB failure makes `recall` return `[]` and log an error span — the run still completes.
- `recall(k=2)` returns exactly 2 of 5 seeded items, reranked best-first (configurable depth + reranking).
- A `remember` write does not block: the turn returns before the write resolves.

→ `workflows/gates.md` for how this folds into the mechanical demo gate.
