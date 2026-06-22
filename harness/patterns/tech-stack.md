# Tech-Stack Rules

Generic engineering rules that hold for **every** project, whatever stack is chosen. The project's *chosen* stack (language, framework, LLM provider/model, database, libraries) is recorded in `spec/architecture.md` under `## Stack`. This file is the permanent doctrine the tech-architect and code-generator follow when filling and implementing that stack — it is not edited per project.

---

## Default Dev Port

All generated projects **must** use **port 8001** as the default development port (not 8000).

Reason: port 8000 is commonly occupied by other local services (FastAPI apps, Django, `http.server`, etc.). Using 8001 avoids startup failures with no code change needed.

- `__main__.py` must hard-code `port=8001` (not 8000) unless overridden by an env var
- README must reference `http://localhost:8001`
- `.env.example` should include `PORT=8001` if the port is configurable

## LLM Model Name Rule

**Always use a current, verified model name — never a deprecated or guessed one.**

- Model names change. Before hardcoding any model identifier, verify it exists by calling the provider's `ListModels` API or checking current documentation.
- The model name must be configurable via an env var (e.g. `APPNAME_LLM_MODEL`) so it can be changed without a code deployment.
- A 404 NOT_FOUND from the LLM API almost always means the model name is wrong — check the name first before debugging anything else.

Current safe defaults (as of 2026):

| Provider | Default model | Notes |
|----------|---------------|-------|
| Anthropic | `claude-sonnet-4-6` | matches `.env.example`; verify against current docs before pinning |
| OpenRouter | `anthropic/claude-sonnet-4-6` | provider-prefixed; routes to the underlying model |
| Google Gemini | `gemini-2.5-flash` | `gemini-2.0-flash` and `gemini-1.5-flash` are unavailable for new users |
| OpenAI | `gpt-4o-mini` | |

## DB Driver Rule

The database driver (e.g. `psycopg2-binary` for PostgreSQL, `asyncpg` for async PostgreSQL) **must be declared in the main `[project.dependencies]` block**, never in `[dependency-groups.dev]` or equivalent dev-only groups.

Reason: Alembic migrations run at deploy/setup time, not just in tests. If the driver is dev-only, `alembic upgrade head` fails in any environment that didn't install dev deps.

## Test Environment Rule

**Tests must use the same database driver as production.** If the production DB is PostgreSQL, tests run against PostgreSQL — not SQLite.

- Tests that pass on SQLite but were never run against PostgreSQL are **not a passing gate**.
- The test database must be set up automatically. Use `conftest.py` to create and tear down the test database — no manual steps.
- The test DB URL is provided via env var (e.g. `TEST_DATABASE_URL`, or reuse `DATABASE_URL` pointing at a `_test` database). The `conftest.py` session fixture creates all tables before tests and drops them after.
- A `.env.test` file (gitignored) or CI environment variable provides the test DB URL. The README must document this.

Example `conftest.py` pattern for PostgreSQL + SQLAlchemy (sync):

```python
import pytest
from sqlalchemy import create_engine
from yourapp.db.models import Base
from yourapp.config.settings import get_settings

@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
```

The `DATABASE_URL` in `.env` (or `.env.test`) must point at a real PostgreSQL test database before running tests.

## LLM / API Test Rule

**Tests and evals run against the real LLM/API using keys loaded from `.env`.** There is no offline-passing requirement; real-key execution is the default and required path for every gate, against the production DB driver (never SQLite if production is PostgreSQL). A stub provider MAY exist as an optional local fallback when a key is genuinely absent, but it is never the gate. The quality bar is perfect, zero errors — edge-case, end-to-end, and UI tests are required, not optional.

- The build and tests load keys programmatically from `.env` (gitignored); confirm a key by presence (bool) only — never echo, print, paste, or commit a secret value.
- A stub is permitted only for an integration whose external system isn't built yet — never as a substitute for the real provider on a path that exists.
- **CI contract:** a runner without secrets cannot pass the real-key gate. Either inject the keys from a secret store, or guard the real-key tests with `pytest.skip` when keys are unset. Skipped is not passed: the Phase 2+ gate is BLOCKED if a required key is missing locally.
