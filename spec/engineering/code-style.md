# Code Style

> **Boilerplate status:** The tech-designer fills in the language-specific FILL-IN sections. The
> Universal Rules and Framework Gotchas below apply to all projects.

---

## Universal Rules

1. **Pragmatic typing** — type the public interfaces: every function crossing a module boundary uses
   typed inputs and outputs (Pydantic, TypeScript interfaces, Go structs). Plain dicts are fine for
   internal/local use where a model would be ceremony — don't force a type on everything, but never
   leak an untyped dict across a module boundary.
2. **One responsibility per file** — if a file does two things, split it.
3. **No comments explaining WHAT** — names carry that; comment only non-obvious WHY.
4. **No dead code** — remove unused imports/functions/variables immediately; don't comment them out.
5. **Fail loudly at startup** — validate required config/env at startup, not silently at runtime.
6. **No hardcoding** — values that could change (URLs, limits, credentials) live in config or env vars.

## To fill in (tech-designer)

- **Naming conventions** — <!-- per language -->
- **File organization** — <!-- by layer / feature / type -->
- **Error handling pattern** — <!-- how errors are represented and propagated -->
- **Logging pattern** — <!-- structured vs. unstructured; always-included fields -->
- **Testing conventions** — <!-- unit-test location, naming, runner -->
- **What NOT to do** — <!-- anti-patterns specific to this stack -->

---

## See also (don't restate these here)

- **ReAct loop, AST safe-executor, reasoning trace** → [`patterns/react-agent.md`](patterns/react-agent.md).
- **LLM provider selection (real-first, no stubs), dirty-`.env` tolerance** →
  [`patterns/llm-providers.md`](patterns/llm-providers.md).
- **DB driver / test environment** → [`tech-stack.md`](tech-stack.md) § Database & Tests.

---

## Framework Gotchas (Python / async FastAPI — keep current)

The backend is **async** (async FastAPI + async SQLAlchemy) and serves a **Next.js/React frontend** — so
errors travel back as **JSON**, not server-rendered HTML.

### Errors are JSON — never an HTML error page

The API returns errors through the standard envelope (`api_error()` → [`../product/05-api.md`](../product/05-api.md))
as JSON; the Next.js frontend renders them. There is no `error.html` template. When an agent run fails,
the error propagates back via the run state's `error` field — surface it as JSON, never re-raise a bare
`HTTPException`:

```python
if state["error"]:
    log.error("run.error", run_id=run_id, error=state["error"])
    return api_error("RUN_FAILED", state["error"], status=500)
```

Every route that runs the agent follows this pattern; the frontend owns presentation.

### Pydantic-settings — `extra="ignore"` + `.env` auto-reload

- Set `extra="ignore"` in `model_config`. `pydantic-settings` reads the **entire** `.env` and validates
  every key; if `.env` carries variables the model doesn't declare (`TEST_DATABASE_URL`, `EDITOR`, CI
  vars), it raises `ValidationError: Extra inputs are not permitted` without it.
- **Dev server auto-restarts on `.env` change.** Run the dev server under a reloader that watches `.env`
  (uvicorn `--reload --reload-include .env`, or `watchfiles`), so editing the API key or a setting takes
  effect without a manual restart. Settings are read at startup (fail-loud, [`code-style.md`](code-style.md)
  Universal Rule 5) — the reload is what makes that ergonomic in dev.

### Async test footguns

- Use `pytest-asyncio`; mark async tests (`@pytest.mark.asyncio` or `asyncio_mode = "auto"`).
- Replace an async `init_db()` with an **async** noop, not a sync lambda:
  `async def _noop(): ...` then `monkeypatch.setattr("<pkg>.graph.runner.init_db", _noop)`. A sync lambda
  breaks `await`.
- Use a file-backed test DB (`tmp_path` for SQLite demos; a `_test` Postgres database for real projects),
  not an in-memory DB — in-memory has shared-state issues across the async engine/connection boundary.
- Drive the async DB with `create_async_engine` + an `AsyncSession`; don't mix sync and async sessions
  against the same engine.
