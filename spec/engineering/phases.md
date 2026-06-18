# Implementation Phases

Agents are built incrementally. This file defines the default phase model. The planner sub-agent adapts it to your specific project.

## Core Principle

**Build the minimal working thing first. Then expand.**

A "working" agent in Phase 2 should demonstrate the core loop end-to-end — even if connections are stubbed, data is hardcoded, and UI is non-existent. Each subsequent phase makes it more real.

## Default Phase Model

The planner sub-agent will customize this for your project, but the general structure is:

### Phase 1 — Domain Models + Data Layer
- Define all core data types (Pydantic models, TypeScript interfaces, etc.)
- Set up the database schema (if applicable)
- No business logic yet
- **Gate (all must pass):**
  1. `pyproject.toml` declares the DB driver in `[project.dependencies]` (e.g. `psycopg2-binary` for PostgreSQL) — never dev-only
  2. `uv run alembic upgrade head` succeeds against the configured database — this must be run and confirmed, not assumed
  3. Basic CRUD unit tests pass
  4. Working tree is clean and committed

### Phase 2 — Core Agent Loop (Stubbed)
- Implement the agent's main loop from start to finish
- **All external calls are hardcoded stubs — zero real API calls, zero network I/O**
- LLM calls return a hardcoded string. Search calls return a hardcoded list. File writes use a temp path.
- The agent must run fully offline. If `pytest` requires an API key to pass, Phase 2 is not done.
- **Gate (all must pass):**
  1. Agent runs end-to-end; at least one record written to DB; run status "completed"
  2. `pytest` passes against the **production DB driver** (e.g. PostgreSQL via psycopg2) — not SQLite
  3. Tests are fully automated: `conftest.py` creates and tears down the test schema; no manual DB setup steps
  4. No LLM API key required to pass tests
  5. **Golden-path UI smoke test passes** (if the project has any UI or HTTP surface). Walks the full primary user flow through `TestClient` AND asserts response content (not only status codes). See `spec/engineering/workflows/golden-path-smoke-test.md`.
  6. **Live-server smoke:** the agent starts the app (`uv run python -m <pkg>`) and hits `/health` plus one real page with `curl`. Both return 200. Exit codes logged in the session report.
  7. **Stub mode is visibly labelled:** every rendered page shows a banner when the LLM provider is stubbed, so a human viewer cannot mistake stub output for real AI output.
  8. **For ReAct-loop agents (Rule #9): the stub simulates at least two iterations** — one where the LLM generates an action, and one where it emits `FINAL ANSWER:`. A stub that returns a final answer on the first call without executing any action does not validate the loop. See `spec/engineering/ai-agents.md` Section 10 for the full pattern.
  9. **Observability baseline:** every node emits a structured (JSON) log bound to `run_id`; every LLM call records tokens + estimated cost on the run; and the reasoning trace (`action_history`) is surfaced to the user, not just logged. Verifiable in the test DB and log output.
  10. **Iteration exhaustion routes to `force_finalize`, not `handle_error`.** A test drives the loop past `max_agent_iterations` and asserts a substantive best-effort answer, not a hard failure.

### Phase 3 — First Real Integration
- Replace the most critical stub with a real external call
- Typically this is the LLM or the primary data source
- **Gate:** Agent runs with one real integration; happy path works with real data

### Phase 4 — Error Handling + Resilience
- Add try/catch, retries, timeouts to all external calls
- Agent should continue (degraded, not crashed) on non-critical failures
- **Gate:** Agent handles all documented failure modes without crashing

### Phase 5 — Remaining Integrations
- Replace remaining stubs with real implementations
- **Gate:** All integrations are real; agent runs fully end-to-end

### Phase 6 — API / CLI Surface
- Add the external API or CLI (if the spec calls for it)
- **Gate:** All specified endpoints/commands work correctly

### Phase 7 — Basic UI (if required)
- Implement the UI from `spec/product/06-ui.md`
- Functional but not polished
- **Gate:** All specified screens/views are present and functional

### Phase 8 — Integration Tests
- Write integration tests that exercise the full system
- **Gate:** Integration tests pass reliably

### Phase 9 — Advanced Observability
- The structured-logging + token/cost baseline already lands in Phase 2 (see gate item 9). This phase adds aggregation on top: per-run metrics, latency tracking, and — if the spec calls for it — trace export (OpenTelemetry GenAI conventions / an LLM tracing backend).
- **Gate:** Per-run token, cost, and latency are queryable in aggregate; errors are surfaced with `run_id` context.

### Phase 10 — Polish + Hand-off
- Fix rough edges, improve error messages, update docs
- Final drift audit: code matches spec
- README is accurate and up to date
- **Gate:** Drift audit passes; README reviewed by user; user accepts hand-off

## Phase Gates

A phase is complete when ALL of the following are true:
1. All code for the phase is committed and pushed
2. All tests for the phase pass
3. Working tree is clean
4. Session report reflects phase completion
5. qa-auditor sub-agent (or manual QA checklist) has signed off
6. For Phase 1 specifically: `alembic upgrade head` has been run against the real DB and succeeded

**Never mark a phase complete if any gate is red.**

**Never claim a phase passes based on tests alone if those tests use a different DB driver than production.** SQLite tests passing does not mean PostgreSQL migrations work.

## Phase Tracking

The current phase is recorded in the active session report and in the git commit messages (`phase-N: [description]`). To see phase history, run `git log --oneline | grep "phase-"`.

## Adapting the Phases

The planner sub-agent may merge, split, or reorder phases based on your project's specifics. For example:
- A pure CLI tool may skip phases 6 and 7
- A project with no database may shrink phase 1
- A project with many integrations may split phase 5 into multiple phases

Whatever the planner decides, the core principle holds: **minimal working thing first**.

---

## Language-Specific Gate Commands

The gate test command depends on the project language. The tech-designer sets this in `spec/engineering/tech-stack.md`; the planner uses it in phase definitions.

| Language | Phase 1 gate | Phase 2 gate |
|----------|-------------|-------------|
| Python | `uv run alembic upgrade head` + `uv run pytest` | `uv run pytest` (PostgreSQL, automated via conftest) |
| TypeScript (Bun) | migration tool + `bun test tests/unit/` | `bun test tests/integration/` |
| TypeScript (Node) | migration tool + `npx vitest run tests/unit/` | `npx vitest run tests/integration/` |
| Go | `migrate up` + `go test ./internal/...` | `go test ./...` |

The Phase 2 gate must pass with **no LLM API key set** regardless of language. The DB URL must be set — tests need a real database, they just don't need a real LLM.

## TypeScript/Bun Phase 2 Test Pattern

```typescript
// tests/integration/pipeline.test.ts
import { describe, it, expect, beforeEach } from "bun:test";

// Use an in-memory or tmp SQLite DB for tests — never real PostgreSQL
// Stub all external HTTP calls with a simple mock

describe("pipeline", () => {
  it("runs end-to-end with stubs", async () => {
    // stub external calls
    // call runner
    // assert DB record created with correct status
  });
});
```
