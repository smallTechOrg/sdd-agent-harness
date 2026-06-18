# DataChat v0.2 — Implementation Plan

Branch: `feature/datachat-v0.2`
Package: `datachat`
Env prefix: `DATACHAT_`

## Phase 1 — Domain Models + DB Schema

**Gate:** `uv run pytest` passes 10/10 unit tests

### Files to create
- `pyproject.toml` — deps: fastapi, uvicorn, langgraph, google-genai, pandas, sqlalchemy, alembic, pydantic-settings, python-multipart, structlog; dev: pytest, httpx
- `src/datachat/__init__.py` — `__version__ = "0.1.0"`
- `src/datachat/config/__init__.py`
- `src/datachat/config/settings.py` — `DATACHAT_` prefix; `resolved_llm_provider` returns `"gemini"` iff key non-empty after stripping inline comments
- `src/datachat/domain/__init__.py`
- `src/datachat/domain/models.py` — `Session`, `Message`, `Run` Pydantic models
- `src/datachat/db/__init__.py`
- `src/datachat/db/models.py` — `SessionRow`, `MessageRow`, `RunRow` SQLAlchemy 2.0
- `src/datachat/db/session.py` — engine + sessionmaker + init_db
- `alembic/script.py.mako` — verbatim template
- `alembic/env.py` — reads `DATACHAT_DATABASE_URL`; `target_metadata = Base.metadata`
- `alembic.ini`
- `tests/conftest.py` — resets `_settings`, `_engine`, `_SessionLocal` singletons
- `tests/unit/test_smoke.py`
- `tests/unit/config/test_settings.py` — uses `setenv("DATACHAT_GEMINI_API_KEY", "")` NOT `delenv`
- `tests/unit/db/test_models.py`
- `tests/unit/domain/test_models.py`

### Alembic sequence
```bash
uv run alembic revision --autogenerate -m "initial"
uv run alembic upgrade head
uv run alembic current   # must show revision hash
```

### Commit
`phase-1: domain models + schema — gate PASSED (10/10 tests)`

---

## Phase 2 — Agent Loop + FastAPI + Tests + README

**Gate:** `uv run pytest` passes 12/12; live-server check green

### Files to create
- `src/datachat/graph/state.py`
- `src/datachat/graph/nodes.py`
- `src/datachat/graph/edges.py`
- `src/datachat/graph/agent.py`
- `src/datachat/graph/runner.py`
- `src/datachat/graph/__init__.py`
- `src/datachat/llm/__init__.py`
- `src/datachat/llm/client.py`
- `src/datachat/llm/providers/base.py`
- `src/datachat/llm/providers/stub.py`
- `src/datachat/llm/providers/gemini.py` — uses `google.genai`, NOT `google.generativeai`
- `src/datachat/llm/providers/factory.py`
- `src/datachat/llm/providers/__init__.py`
- `src/datachat/tools/__init__.py`
- `src/datachat/tools/pandas_executor.py` — frozenset allowlist, regex extraction
- `src/datachat/prompts/plan_action.md`
- `src/datachat/observability/__init__.py`
- `src/datachat/observability/events.py`
- `src/datachat/api/__init__.py` — create_app() + lifespan
- `src/datachat/api/_common.py`
- `src/datachat/api/health.py`
- `src/datachat/api/sessions.py`
- `src/datachat/api/chat.py`
- `src/datachat/__main__.py`
- `tests/integration/__init__.py`
- `tests/integration/test_pipeline.py`
- `tests/integration/test_golden_path.py`
- `README.md`

### Key correctness requirements
- Stub branches on `<node:plan>` tag, not prose
- Tests use `monkeypatch.setenv("DATACHAT_GEMINI_API_KEY", "")` (not delenv) so .env file doesn't bleed in
- Gemini provider uses `from google import genai` + `genai.Client(api_key=...)`
- Stub banner visible in all HTML responses when `llm_provider == "stub"`

### Commit
`phase-2: stubbed ReAct agent loop + FastAPI API + README — gate PASSED (12/12 tests)`
