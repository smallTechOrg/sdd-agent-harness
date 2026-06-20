# Usage-spec: SQLAlchemy 2.0 (async) (+ aiosqlite / asyncpg)

**Version: `sqlalchemy` 2.0.x · `aiosqlite` 0.2x · `asyncpg` 0.3x** (verify latest — a bump REFRESHES this file)
**Stamped: 2026-06**

Guards: `persistence.md` (`agent/db.py`), `observability-and-evals.md` (spans), `memory.md`. The core is
**async end-to-end** — one engine, one `async_sessionmaker`, `create_all` local-first.

## Engine + sessionmaker (the one DB accessor)
```python
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

engine = create_async_engine(get_settings().database_url)
_sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

def get_sessionmaker() -> async_sessionmaker:
    return _sessionmaker
```
- ✅ `create_async_engine` + `async_sessionmaker` (the 2.0 async API), `expire_on_commit=False` so objects
  stay usable after `commit()`.
- ❌ **NEVER** `create_engine` (sync) or `sessionmaker` (sync) — they block the event loop.
- ❌ **NEVER** `psycopg2` for Postgres — use `postgresql+asyncpg://`. SQLite local is `sqlite+aiosqlite:///`.
  Only `APP_DATABASE_URL` flips between rungs; **no code change** (`C-PROD-DRIVER`).

## Models — 2.0 typed mapping (`Mapped[...]` + `mapped_column`)
```python
class Base(AsyncAttrs, DeclarativeBase): ...

class Run(Base):
    __tablename__ = "runs"
    id:            Mapped[str]   = mapped_column(String, primary_key=True, default=_uuid)
    status:        Mapped[str]   = mapped_column(String, default="running")
    answer:        Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens:  Mapped[int]   = mapped_column(Integer, default=0)   # usage/cost first-class (C-USAGE-COST)
    output_tokens: Mapped[int]   = mapped_column(Integer, default=0)
    cost_usd:      Mapped[float] = mapped_column(Float, default=0.0)
    thread_id:     Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # multi-turn
    attributes:    Mapped[dict]  = mapped_column(JSON, default=dict)   # JSON works on BOTH sqlite & postgres
```
- ✅ Use `Mapped[...]` + `mapped_column(...)` (2.0 style). ❌ Not the 1.x `Column(...)` class-attr style.
- ✅ `JSON` column type is portable across SQLite and Postgres — use it (the spans `attributes`); don't reach
  for `JSONB` in the portable model.

## Sessions — `async with`, explicit commit, `await execute`
```python
from sqlalchemy import select

async with get_sessionmaker()() as s:                 # note the DOUBLE call: ()() — maker, then session
    rows = (await s.execute(select(Run).where(Run.id == rid))).scalars().all()
    s.add(Run(...))
    await s.commit()                                  # commit is EXPLICIT — no autocommit
```
- ✅ `select(...)` + `await s.execute(...)` then `.scalars().all()` / `.scalar_one()`. ❌ Not the legacy
  `s.query(Run)` API (sync-flavoured, deprecated in 2.0).
- ✅ Always `await s.commit()` explicitly; the session is `async with`-scoped.

## init_db — create_all local-first (NOT for prod schema changes)
```python
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # run_sync wraps the sync DDL on the async conn
```
- ✅ `await conn.run_sync(Base.metadata.create_all)` — DDL is sync, wrapped via `run_sync` on the async conn.
- ⚠️ `create_all` makes **new** tables but never **alters** existing ones — fine for SQLite dev; on a deployed
  Postgres use alembic migrations, not auto-`create_all` (`persistence.md` § Migrations, moved to `/deploy`).

## Test DB
- ✅ File-backed test DB (a temp file), **not** `:memory:` (in-memory loses tables across async connections).
  pytest-asyncio with an async no-op/real `init_db`, a resettable settings singleton (`C-PROD-DRIVER`).
