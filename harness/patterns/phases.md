# Implementation Phases

Agents are built incrementally. This file defines the default phase model. The tech-architect sub-agent adapts it to your specific project.

## Core Principle

**Build the minimal working thing first. Then expand.**

A "working" agent in Phase 2 should demonstrate the core loop end-to-end against the real LLM/API (keys from `.env`), even if data is thin and UI is minimal. Each subsequent phase makes it more complete.

## Default Phase Model

The tech-architect sub-agent will customize this for your project, but the general structure is:

### Phase 1 — Domain Models + Data Layer
- Define all core data types (Pydantic models, TypeScript interfaces, etc.)
- Set up the database schema (if applicable)
- No business logic yet
- **Gate (all must pass):**
  1. `pyproject.toml` declares the DB driver in `[project.dependencies]` (e.g. `psycopg2-binary` for PostgreSQL) — never dev-only
  2. `uv run alembic upgrade head` succeeds against the configured database — this must be run and confirmed, not assumed
  3. Basic CRUD unit tests pass
  4. Working tree is clean and committed

### Phase 2 — Core Agent Loop (Real Integration)
- Implement the agent's main loop from start to finish.
- All external calls hit the real provider (LLM/API/search) using keys loaded from `.env`.
- The agent runs end-to-end against the real LLM; tests assert on real responses (shape/content), not hardcoded strings.
- A stub provider MAY remain as an optional fallback for offline development, but it is not required and tests are NOT expected to pass with keys unset.
- **Gate (all must pass):**
  1. Agent runs end-to-end; at least one record written to DB; run status "completed"
  2. `pytest` passes against the **production DB driver** (e.g. PostgreSQL via psycopg2, not SQLite) **with** real LLM/API keys loaded from `.env`
  3. Tests are fully automated: `conftest.py` creates and tears down the test schema; no manual DB setup steps
  4. Real LLM/API keys are present in `.env` and the suite exercises the real provider — no all-stubbed run is accepted as the Phase 2 gate
  5. **Golden-path UI smoke test passes** (if the project has any UI or HTTP surface). Drives the full primary user flow through `TestClient` against the real LLM/API and asserts real response content (not only status codes). Edge-case and end-to-end UI assertions are required, not optional.
  6. **Live-server smoke:** the agent starts the app (`uv run python -m <pkg>`) and hits `/health` plus one real page with `curl`, exercising the live LLM/API path. Both return 200 and the page shows real AI output. Exit codes logged in the session report.

### Phase 3 — Remaining Integrations
- Wire up any secondary providers or data sources not covered by the Phase 2 core loop.
- **Gate:** Each integration runs for real; happy path works end-to-end with real data.

### Phase 4 — Error Handling + Resilience
- Add try/catch, retries, timeouts to all external calls
- Agent should continue (degraded, not crashed) on non-critical failures
- **Gate:** Agent handles all documented failure modes without crashing

### Phase 5 — Full Integration Pass
- Complete any remaining secondary integrations and verify the whole system runs against real services.
- **Gate:** All integrations are real; agent runs fully end-to-end

### Phase 6 — API / CLI Surface
- Add the external API or CLI (if the spec calls for it)
- **Gate:** All specified endpoints/commands work correctly

### Phase 7 — Basic UI (if required)
- Implement the UI from `spec/ui.md`
- Functional but not polished
- **Gate:** All specified screens/views are present and functional

### Phase 8 — Integration Tests
- Write integration tests that exercise the full system against real services, including edge cases, error paths, and any UI journey.
- **Gate:** Integration, edge-case, end-to-end, and UI tests pass reliably against the real LLM/API

### Phase 9 — Observability + Logging
- Add structured logging, metrics, and monitoring
- **Gate:** Every major operation produces a log entry; errors are surfaced

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

**Never claim Phase 2+ passes on stubbed providers** — the gate runs against the real LLM/API with keys from `.env`.

## Phase Tracking

The current phase is recorded in the active session report and in the git commit messages (`phase-N: [description]`). To see phase history, run `git log --oneline | grep "phase-"`.

## Adapting the Phases

The tech-architect sub-agent may merge, split, or reorder phases based on your project's specifics. For example:
- A pure CLI tool may skip phases 6 and 7
- A project with no database may shrink phase 1
- A project with many integrations may split phase 5 into multiple phases

Whatever the tech-architect decides, the core principle holds: **minimal working thing first**.

---

## Language-Specific Gate Commands

The gate test command depends on the project language. The tech-architect sets the exact command per phase in `reports/implementation-plan.md`, honoring the test rules in `harness/patterns/tech-stack.md`.

| Language | Phase 1 gate | Phase 2 gate |
|----------|-------------|-------------|
| Python | `uv run alembic upgrade head` + `uv run pytest` | `uv run pytest` (PostgreSQL, automated via conftest) |
| TypeScript (Bun) | migration tool + `bun test tests/unit/` | `bun test tests/integration/` |
| TypeScript (Node) | migration tool + `npx vitest run tests/unit/` | `npx vitest run tests/integration/` |
| Go | `migrate up` + `go test ./internal/...` | `go test ./...` |

The Phase 2 gate runs with **real LLM/API keys loaded from `.env`** regardless of language; both the DB URL and the provider key(s) must be set.

## TypeScript/Bun Phase 2 Test Pattern

```typescript
// tests/integration/pipeline.test.ts
import { describe, it, expect, beforeEach } from "bun:test";

// Use the production DB driver via conftest-style setup/teardown — never SQLite-as-a-substitute
// Call the real LLM/API using keys from .env

describe("pipeline", () => {
  it("runs end-to-end against the real provider", async () => {
    // call runner against the real provider
    // assert DB record created with correct status
  });
});
```
