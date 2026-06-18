# Project Layout — Canonical Structure

All agents built from this boilerplate follow this layout exactly. The files below (`settings.py`,
`session.py`, `models.py`, `graph/*`, `api/*`, `conftest.py`, `test_pipeline.py`) are standard
FastAPI/SQLAlchemy/LangGraph shapes — generate them idiomatically from this tree and the rules below.
The one exception is `alembic/script.py.mako`, which nothing generates — it's given verbatim under
§ Phase 1.

---

## The repo root IS the agent project

There is **no `<agent-slug>/` wrapper**. Boilerplate files (`spec/`, `reports/`, `.github/`,
`AGENTS.md`, `CLAUDE.md`) coexist with project files at the repo root.

**All application source code lives inside `src/`.** Never place HTML, CSS, JavaScript, Python
packages, templates, or data files at the repo root. The root is for project-level config only
(`pyproject.toml`, `alembic.ini`, `README.md`, `.env.example`) plus the preserved boilerplate. This
applies to every stack — Python packages, static web apps, TypeScript projects, anything. If you're
about to create an application file at the root, stop and put it in `src/` instead.

---

## README Requirements (canonical home — Mandatory)

The README is the first thing a user touches. A wrong README fails the entire build regardless of
whether the code works. Every generated README must:

1. **State "all commands run from the repo root"** as a blockquote or bold warning at the very top.
   The repo root IS the project — there is no subdirectory to `cd` into.
2. **State the exact working directory** at the top of every shell code block. "Run from project root"
   is enough only because the root is the project; never leave it implicit for a nested path.
3. **Prefix every command with the package-manager runner** — for Python + uv, every `alembic`,
   `pytest`, `python` is `uv run …`. Bare commands fail unless the venv is manually activated, which
   users won't do.
4. **Include `uv run alembic current` after `upgrade head`** so the user can verify tables were created
   (blank output = silent failure).
5. **Stay accurate** — every README command is tested before a phase is marked complete (see
   `ai-agents.md` Rule 1). If a command fails, fix the README before claiming the phase is done.

---

## Directory Tree

```
<repo root>                           ← repo root IS the agent project
├── src/
│   └── <package>/                    ← Python package (snake_case matches slug)
│       ├── __init__.py               ← __version__ = "0.1.0"
│       ├── api/                      ← FastAPI routers
│       │   ├── __init__.py           ← create_app() factory + lifespan
│       │   ├── _common.py            ← ok(), api_error()
│       │   └── <resource>.py         ← one router per domain entity
│       ├── config/
│       │   └── settings.py           ← Pydantic BaseSettings with env prefix
│       ├── db/
│       │   ├── models.py             ← SQLAlchemy 2.0 declarative (Mapped types)
│       │   └── session.py            ← engine + sessionmaker + init_db
│       ├── domain/
│       │   ├── __init__.py           ← re-exports all domain models
│       │   └── <entity>.py           ← Pydantic BaseModel per entity
│       ├── graph/
│       │   ├── agent.py              ← StateGraph compiled once at startup
│       │   ├── nodes.py              ← node functions: (state) → state
│       │   ├── edges.py              ← conditional routing functions
│       │   ├── state.py              ← AgentState TypedDict
│       │   └── runner.py             ← run_agent() entry point
│       ├── llm/
│       │   └── model.py              ← init_chat_model accessor (routing, structured output, caching)
│       ├── tools/                    ← pure functions: (inputs) → domain models
│       ├── mcp/                      ← MCP clients + servers (all tools — internal + external)
│       ├── memory/                   ← working/short-term memory + context assembly (long-term: earns its place)
│       ├── retrieval/                ← embeddings, chunking, vector search (RAG) — earns its place
│       ├── guardrails/               ← action-safety (baseline); input/output + HITL earn their place
│       ├── prompts/                  ← LLM prompt templates (.md files)
│       └── observability/
│           └── events.py             ← structlog configuration
├── evals/                            ← eval datasets + harness (real model, loose asserts), runs in CI
├── tests/                            ← tests at repo root, NOT inside src/
│   ├── conftest.py                   ← settings singleton reset fixture
│   ├── unit/                         ← test_smoke, config, db, domain, graph
│   └── integration/
│       └── test_pipeline.py          ← real run (loose asserts), one DB record, status=completed
├── alembic/
│   ├── env.py                        ← reads DB URL from settings; target_metadata = Base.metadata
│   ├── script.py.mako               ← REQUIRED — alembic revision fails without it
│   └── versions/0001_initial.py      ← generated by: uv run alembic revision --autogenerate -m "initial"
├── spec/                             ← preserved from boilerplate
├── reports/sessions/                 ← session report created BEFORE Phase 1
├── .github/ · AGENTS.md · CLAUDE.md  ← preserved from boilerplate
├── pyproject.toml · alembic.ini · .env.example
└── README.md                         ← replaces the boilerplate README
```

**Critical:** `tests/` is at the repo root — **not** inside `src/`. `pyproject.toml` must set
`testpaths = ["tests"]`.

The `mcp/`, `memory/`, `guardrails/`, and `evals/` directories implement the agentic stack layers —
each is defined once in [`agentic-architecture.md`](agentic-architecture.md) and its pattern doc. They're
part of the raised default baseline, **real in Phase 1**. `retrieval/` (and long-term memory inside
`memory/`) is earns-its-place — create it only when a later phase needs it. Create only the layer dirs
the agent actually uses, per `02-architecture.md` § Agentic stack layers used.

---

## Phase 1 alembic sequence (mandatory, in order)

All commands run from the **repo root** (where `alembic.ini` and `pyproject.toml` live).
`alembic/script.py.mako` must exist first — **create it by hand**; nothing generates it, and
`alembic revision --autogenerate` fails with `FileNotFoundError` without it:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Then run the sequence:

```bash
# 1. Create alembic/ (env.py, alembic.ini, script.py.mako)
# 2. Define all SQLAlchemy models in src/<package>/db/models.py
# 3. Generate the initial migration (DB must be reachable, DATABASE_URL set):
uv run alembic revision --autogenerate -m "initial"
# 4. Apply it:
uv run alembic upgrade head
# 5. Verify — must show the revision hash, not blank:
uv run alembic current
```

**Phase 1 is not complete until `alembic current` shows a revision.** Blank output means no migration
was applied.

---

## Rules

1. **Agent code goes in `src/<package>/`** at the repo root — never in a `<agent-slug>/` wrapper, never
   at the root itself.
2. **No repository pattern** — direct SQLAlchemy queries in graph nodes and API handlers.
3. **`graph/` not `agent/`** — directory name matches the canonical convention.
4. **TypedDict state** — not dataclass or Pydantic model.
5. **Tools are pure functions** — `(inputs) → domain model`, no class instantiation.
6. **Prompts are `.md` files** in `<package>/prompts/` — loaded at runtime.
7. **LLM via `init_chat_model`** — construct the model through LangChain's `init_chat_model` behind a
   thin `llm/model.py` accessor; never call a provider SDK directly in nodes, and no bespoke `LLMClient`.
8. **FastAPI response envelope** — every async route returns `ok(data)` or raises `api_error()` (JSON).
9. **Settings singleton** must be resettable via `monkeypatch.setattr(m, "_settings", None)`.
10. **Phase 1 gate runs against the real model** — DB URL set + the provider API key set (locally from
    `.env`, in CI from a secret), with loose assertions; there is no stub/offline path (see `phases.md`
    and `patterns/llm-providers.md`).
