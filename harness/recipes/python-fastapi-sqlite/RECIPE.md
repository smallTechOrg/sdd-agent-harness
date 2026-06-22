# python-fastapi-sqlite Recipe

A clone-and-rename baseline for FastAPI + LangGraph + SQLite + Anthropic agents.
All tests pass out of the box. Generators extend this recipe — they do not rewrite it.

---

## 1. What this recipe is

- A minimal but complete agentic stack: HTTP API → LangGraph → LLM → SQLite.
- The `transform_text` node is the **capability slot** — one real LLM call, one DB write, one response.
- Unit tests pass without any API key. Integration tests require a real Anthropic key.

---

## 2. Rename checklist

Replace every occurrence of `agent` (the Python package name) with your slug (e.g. `mybot`):

| Location | What to change |
|---|---|
| `src/agent/` directory | Rename to `src/<slug>/` |
| `pyproject.toml` → `name = "agent"` | Change to `name = "<slug>"` |
| All `from agent.` imports | Change to `from <slug>.` |
| All `import agent` | Change to `import <slug>` |
| `AGENT_` env prefix in `settings.py` | Change `env_prefix="AGENT_"` to `env_prefix="<SLUG>_"` |
| `.env.example` `AGENT_*` keys | Rename to `<SLUG>_*` |
| `alembic/env.py` import | Update `from agent.config…` / `from agent.db…` |
| `conftest.py` imports | Update all `agent.*` references |
| `__main__.py` | Update `"agent.api:app"` to `"<slug>.api:app"` |

---

## 3. What to replace (the capability slot)

`src/agent/graph/nodes.py` contains `transform_text` — replace:

- `src/agent/prompts/transform.md` — write the new system prompt
- `transform_text` node logic — call whatever LLM/tool your spec requires
- `AgentState` fields in `graph/state.py` — add domain-specific fields
- `RunRow` columns in `db/models.py` if the spec adds output fields
- `RunRequest` / `RunResponse` in `domain/run.py` if the API shape changes

Everything else (graph structure, runner, API, DB session, settings) is already wired and tested.

---

## 4. What NOT to change

These are tested and correct — changing them breaks the gate:

- Settings singleton pattern (`_settings`, `get_settings()`)
- Session/engine pattern (`_engine`, `_SessionLocal`, `create_db_session()`, `get_session()`)
- `ok()` / `api_error()` envelope
- `create_app()` factory + lifespan
- `conftest.py` fixture names (`_reset_settings_singleton`, `_isolated_db`, `_require_api_key`)

---

## 5. Verify after rename

```bash
# Unit tests — must pass with no API key
uv run pytest tests/unit/ -v

# Integration tests — requires real key in .env
uv run pytest tests/ -v
```

---

## 6. Frontend

The frontend is a Next.js static export (`output: 'export'`) served by FastAPI at `/app`.
Single server — `build.sh` builds the frontend then starts the Python process.

**Rename checklist (frontend):**
- `frontend/package.json` → change `name` from `agent-frontend` to `<slug>-frontend`
- `frontend/src/app/layout.tsx` → update `metadata.title` and `metadata.description`

**Capability slot:**
- `frontend/src/app/page.tsx` — replace the transform form with your capability's UI
- Stub pages (e.g. `history/`) are clearly labelled placeholders; wire them up phase by phase

**Build:**
```bash
cd frontend && pnpm build   # generates frontend/out/; FastAPI mounts it at /app
```

**API calls from the frontend** use relative paths (e.g. `fetch('/runs', ...)`).
Since both are on the same origin (`localhost:8001`), no CORS or proxy config is needed.

---

## 7. Gate commands (copy into spec/roadmap.md)

```
Phase 1 gate:  uv run pytest tests/unit/ -v
Phase 2 gate:  uv run pytest tests/ -v
Live smoke:    uv run python -m agent & sleep 2 && curl -s http://localhost:8001/health
UI smoke:      ./build.sh & sleep 5 && curl -s http://localhost:8001/app/ | grep -i transform
```
