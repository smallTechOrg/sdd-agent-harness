# Code Style

## Universal Rules

1. **Types at boundaries** — every function crossing a module boundary uses typed inputs/outputs (Pydantic, TypedDict)
2. **One responsibility per file** — if a file does two things, split it
3. **No comments explaining WHAT** — only comment WHY something non-obvious is done
4. **No dead code** — remove unused imports, functions, variables immediately
5. **Fail loudly at startup** — validate all required env vars at startup
6. **No hardcoding** — URLs, model names, limits go in settings

## Naming Conventions

- **Packages/modules:** `snake_case`
- **Classes:** `PascalCase`
- **Functions/variables:** `snake_case`
- **Constants:** `UPPER_SNAKE_CASE`
- **Graph nodes:** `snake_case` function names (e.g., `load_data`, `analyze`, `finalize`)

## File Organization

Files grouped by layer:
```
src/data_analysis_agent/
├── api/          ← HTTP routing, one router per domain entity
├── config/       ← Settings, env var loading
├── db/           ← SQLAlchemy models, session, init
├── domain/       ← Pydantic models (Dataset, QueryRecord)
├── graph/        ← LangGraph: state, nodes, edges, agent, runner
├── llm/          ← LLM client + providers (gemini, stub)
├── prompts/      ← .md prompt templates
└── tools/        ← Pure functions: CSV parsing, data sampling
```

## Error Handling Pattern

- Every external call (LLM, filesystem) wrapped in try/except
- On fatal error: set `state["error"] = str(e)` and let conditional edges route to `handle_error`
- Pipeline failures are caught on the background thread and recorded on the QueryRecord
  (`status="failed"`, `error_message`); the failed turn renders inline — never a bare 500
- Log every error with structlog including `run_id` and `dataset_id`

## Logging Pattern

structlog, structured JSON in production. Key fields always present:
- `event` — what happened
- `run_id` — pipeline run ID (when in graph context)
- `dataset_id` — which dataset
- `level` — INFO / WARNING / ERROR

## Testing Conventions

- Tests in `tests/` at repo root (not inside `src/`)
- `tests/unit/` — pure function tests, no DB, no network
- `tests/integration/` — end-to-end pipeline test, SQLite tmp file
- Runner: `uv run pytest`
- All tests must pass with zero env vars set (besides DB URL via monkeypatch)

## What NOT to Do

- Don't call `google.generativeai` or `genai` directly in nodes — use `LLMClient`
- Don't use `session.execute(text(...))` raw SQL — use SQLAlchemy ORM methods
- Don't use `os.environ.get(...)` directly — always go through `get_settings()`
- Don't use `git add -A` — always stage specific files

---

## Framework Gotchas

### Starlette ≥ 1.0 `TemplateResponse` signature

```python
# CORRECT
return templates.TemplateResponse(request, "page.html", {"foo": bar})

# WRONG — fails with TypeError
return templates.TemplateResponse("page.html", {"request": request, "foo": bar})
```

### LLM provider selection and stubs

1. **`provider=auto` by default** — real when `DATAANALYSIS_GEMINI_API_KEY` is set, stub otherwise.
2. **Stub branches on `<node:analyze>` tag** injected by the analyze node — never on prose keywords.
3. **Stub answer is article-shaped** — a plausible paragraph, not a bullet list.
4. **UI shows stub-mode banner** on every page when `resolved_llm_provider == "stub"`.
5. **Strip inline `.env` comments** — `DATAANALYSIS_GEMINI_API_KEY=abc  # my key` must not include `# my key` in the key value.

### Pydantic-settings

Always set `extra="ignore"` in `model_config`.

### Pipeline errors

Record pipeline failures on the QueryRecord (`status="failed"`, `error_message`) and render the failed
turn inline — never a bare 500. API-level validation (`api_error`) raises `HTTPException` with a
structured `{code, message}` detail.
