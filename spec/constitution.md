# Constitution — the non-negotiables every build inherits

**Version 1.0.0** · SemVer · this file is the law every capability, recipe, and gate inherits. It is short on
prose and long on *enforcement*: **each rule maps to a mechanical check** (a gate line, a hook, a lint, or a
test) so a constitution is something the build *proves*, not something it preaches. If a rule here has no
mechanical owner, that is a bug to fix — not a rule to delete.

How to read a rule: **ID** · **MUST/SHOULD** · the rule · **→ enforced by** (the exact mechanical owner;
`gates.md` checks are numbered DEMO 1–8 / PROD P1–P4). A MUST with a red check blocks "done." A SHOULD is
advisory: a reviewer flags it, it does not block the gate by itself.

Versioning: bump **MAJOR** when a MUST is removed or its meaning changes (existing builds may break); **MINOR**
when a MUST/SHOULD is added; **PATCH** for wording/owner-path fixes. Record every change in the changelog
below. Capabilities and recipes inherit the version current at build time.

---

## The two-zone model (which artifact is the source of truth)

These rules span **two zones**, and which artifact is authoritative differs between them (the honest framing
the harness leads with — `harness/harness.md` § Two zones, `reports/archaeology/SPEC-RECONCILIATION.md` § F).
Claiming "pure spec-as-source" end to end would be a lie the repo can't back, so we don't:

- **The reused, version-pinned TESTED CORE — *code is truth*, like a framework dependency.** The async
  server, the ReAct loop (`force_finalize` + `max_iterations` sizing + AST-eval action-safety), `config.py`,
  the `ok()`/`api_error()` envelope, session-scoped resources, usage/cost columns, the `/traces` dashboard,
  the gate harness, the UI shell, SQLite + `create_all`. This ships **already tested**; `/build` configures
  it, it does **not** regenerate it. Most C-* rules below are guarantees the core already keeps.
- **The GENERATED DOMAIN — *spec is truth*.** Capability nodes, tools, prompts, the EARS evals, and the
  domain UI screens. Here the spec authors the behavior; `/build` fills only these seams.

Every C-* rule still applies across both zones — the difference is only *who* you fix when a check goes red:
a core rule means fix the recipe/core; a domain rule means fix the spec.

---

## A. Configuration & secrets (the silent-failure killers)

- **C-ENV-STRIP** · MUST · Strip inline `#` comments and surrounding whitespace from every env value before
  use. pydantic-settings does **not**; an `APP_LLM_API_KEY=sk-xxx # prod key` value silently 401s on the real
  run while the build is green. One field validator, highest-ROI rule in this file.
  → enforced by: a unit test feeding the commented value via an **env var** (`monkeypatch.setenv("APP_LLM_API_KEY", ...)`
  or a tmp `.env`, **never an init kwarg** — kwargs aren't `APP_`-mapped and the `SecretStr` field keeps its
  empty default, a false-RED; `patterns/model-and-providers.md` §Gate) asserts the parsed value is clean
  (DEMO 2); the real run (DEMO 5) would 401 otherwise.
- **C-ENV-IGNORE** · MUST · `extra="ignore"` in the pydantic-settings `model_config`, so undeclared `.env`
  keys (`TEST_DATABASE_URL`, CI vars) don't raise at startup.
  → enforced by: `agent/config.py` recipe + a test that loads settings with an extra key present (DEMO 2).
- **C-SECRET-TYPE** · MUST · API keys are `SecretStr`; `.get_secret_value()` is called **only** at the use
  boundary (constructing the model client). Never log, print, or `repr` a secret. A secret-bearing file is
  gitignored **before** it is created. Agents never read `.env` unless asked, and never commit a secret even
  if asked.
  → enforced by: the secret-scan git hook (`.githooks/`) + PROD P4 (`git grep` finds no key in tracked files
  or build context).

## B. Agent runtime behavior (the ReAct core)

- **C-FINALIZE** · MUST · `force_finalize` never returns a blank answer: backwards-scan for a finish call →
  else the last AIMessage text → else the last ToolMessage; coerce list-of-parts content before extraction.
  A test must drive **past `max_iterations`** into `force_finalize` and assert a non-empty answer.
  → enforced by: `test_force_finalize` in the suite (DEMO 2); a blank answer also fails the outcome eval
  (DEMO 6).
- **C-MAXITER** · MUST · `max_iterations` is sized to the **worst-case** tool depth, not the happy path. Too
  tight = silent empty answers. It is `APP_`-configurable.
  → enforced by: the ReAct loop test asserts ≥2 iterations on a multi-tool path (DEMO 2).
- **C-DEGRADE** · MUST · Every external call (API/DB/LLM) is wrapped, logged, and the agent continues on a
  non-critical failure; terminal nodes clean up their resources.
  → enforced by: a fault-injection test (a tool raises) asserts the run still completes (DEMO 2).
- **C-ACTION-SAFETY** · MUST · Code-executing tools use **AST-validated eval** — `ast.parse` + walk +
  restricted eval with empty `__builtins__`, a blocked-attrs frozenset, and an allowed-names allowlist.
  **Never regex dispatch** (it breaks on the chained pandas/SQL the LLM generates and is an injection
  surface).
  → enforced by: a test feeds a disallowed construct and asserts it is rejected (DEMO 2); `forbid_tools`
  trajectory assertion (DEMO 6) proves no ungated mutating tool fired.
- **C-SESSION-SCOPE** · MUST · Any resource reused across turns (a DataFrame, a parsed file, an index, a
  pasted document/transcript — regardless of size/cost) is keyed by `session_id` and persists across
  follow-ups; released **only** on explicit session delete. Per-question release is a correctness bug
  (`SESSION_DATA_LOST` on Q2). The **read path** matters as much as the populate path: the query tool finds
  the session via the `current_session_id` ContextVar set by `runner.py` around `graph.ainvoke` — NOT a
  model-supplied `session_id` parameter (the loop injects no session context; a `session_id` arg would be
  hallucinated, so the tool always reports "no data loaded"). `patterns/persistence.md` § read path.
  → enforced by: the two-turn gate (DEMO 5, Q2 on the same session) fails if Q2 can't see Q1's resource —
  and Q1 itself fails if the read path is broken (the agent answers "no data loaded").
- **C-USAGE-COST** · MUST · `input_tokens`, `output_tokens`, `cost_usd`, and `thread_id` are first-class
  columns on `runs` from Phase 1; `usage_metadata` is read via a type-guarded `.get()`.
  → enforced by: a persistence test asserts the columns populate after a run (DEMO 2); visible in `/traces`
  (DEMO 8).
- **C-MULTITURN-PROMPT** · SHOULD · On multi-turn, read the raw checkpoint dict (`cp['channel_values']`) and
  refresh the SystemMessage each turn so the prompt is never stale.
  → enforced by: reviewer check; the two-turn gate (DEMO 5) catches the worst regressions.

## C. The HTTP / response contract

- **C-ENVELOPE** · MUST · Every route returns `ok(data)` or raises `api_error(code, status)`. A failed run
  reads `state['error']`, logs it with `run_id`, and returns `api_error('RUN_FAILED', status=500)`. No
  `error.html`, no bare 500.
  → enforced by: `agent/server.py` recipe + a route test asserting the JSON envelope on both paths (DEMO 2);
  `/health` returns `{"ok": true}` (DEMO 4).
- **C-PORT** · MUST · The dev server runs on **port 8001** (not 8000); the README references
  `localhost:8001`.
  → enforced by: `config.py` default + the gate boots and curls `:8001` (DEMO 3–4).

## D. Testing & the gate (the proof)

- **C-TWO-TURN** · MUST · The gate POSTs Q1 then a follow-up Q2 on the **same session**; any Q2 error fails
  the gate even if Q1 passed.
  → enforced by: DEMO 5.
- **C-LIVE-E2E** · MUST · The gate boots the real app (`python -m agent`) and exercises it over HTTP
  (`/health` + a real `POST /runs`), logging exit codes. TestClient/FakeModel alone is insufficient.
  → enforced by: `demo_gate.sh` (DEMO 3–5).
- **C-ASSERT-CONTENT** · MUST · Tests assert rendered **content** (input reflected, real structure, length
  sanity), not just status codes.
  → enforced by: route/UI content assertions in the suite (DEMO 2) + DEMO 8 (`/traces` shows the run).
- **C-LOOP-RUNS** · MUST · A test proves the ReAct loop runs **≥2 iterations** (≥1 action + finish) — the
  loop, not just the nodes.
  → enforced by: the loop iteration test (DEMO 2).
- **C-OUTCOME-EVAL** · MUST · A small fixed dataset + ≥1 rubric, real model, loose asserts: a `200` with a
  **wrong answer fails**. The judge is **multi-sampled** with a margin so the verdict is deterministic.
  → enforced by: `stable_outcome_eval` in `test_demo_gate` (DEMO 2) and `agent.gate_eval` (DEMO 6).
- **C-EARS-EVAL-BOUND** · MUST · Every EARS line in `spec/capabilities/*.md` carries an `[@eval: path::case]`
  token binding it to an executable check; a lint fails the build if any criterion is unbound. The agent
  fills the token; the non-coder never sees it.
  → enforced by: the EARS→eval lint (DEMO 1, run before the suite).
- **C-PROD-DRIVER** · MUST · Tests use the **production DB driver** (driver in main deps, not dev-only) and a
  **file-backed** test DB (not in-memory); pytest-asyncio with an async no-op `init_db` and a resettable
  settings singleton. Never `psycopg2` — `asyncpg` on Postgres.
  → enforced by: the conftest fixture (DEMO 2) + PROD P1 reuses the same suite on Postgres.
- **C-NO-FALSE-PASS** · MUST · Never claim a test passed without running it; never mark complete with any
  check red. "I tested it and it works" is not a pass — `echo $?` after `make gate` is.
  → enforced by: qa-auditor confirms the literal exit code of `make gate` (DEMO 1–8).

## E. Process & git

- **C-NO-ADD-ALL** · MUST · Never `git add -A` or `git add .` — stage specific files only (it sweeps stray
  leftovers and secrets into a commit).
  → enforced by: agent-builder Non-Negotiables + the pre-commit hook (`.githooks/`).
- **C-COMMIT-PUSH** · MUST · Commit and push are **one indivisible action** (`commit && push`); an unpushed
  commit doesn't exist.
  → enforced by: agent-builder Non-Negotiables; reviewer flags a dangling local commit.
- **C-BRANCH-PR** · MUST · A PR is open before the first feature-branch commit; `main` is boilerplate-only;
  the branch is `feature/<slug>-<date>`.
  → enforced by: the branch-guard git hook blocks app code on `main` (`.githooks/`).
- **C-UNATTENDED** · MUST · After one intake round (API key + runtime model collected at **Q4**) **and the
  single scope+stack+plan approval** (after the spec/plan draft + pre-flight, before generation —
  `workflows/build.md` §2b), the build runs unattended to the green gate — no further pauses, no mid-build
  "Proceed?", no asking for the key later. Self-diagnose from logs + `/traces` before asking the user; pause
  only on a true blocker.
  → enforced by: `workflows/build.md` § Autonomy/§2b + agent-builder; deviations are visible in the run log.
- **C-ASKUSER** · MUST · `AskUserQuestion` is loaded via ToolSearch **before** intake; intake and the single
  scope+stack+plan approval (`workflows/build.md` §2b) use it (never plain text).
  → enforced by: `workflows/build.md` intake/§2b step; reviewer check.

## F. Stack defaults (ratified)

- **C-MODEL-VERIFIED** · MUST · The runtime model id is current/verified against the provider and
  env-configurable (`APP_LLM_MODEL`); a 404 ≈ a wrong model name.
  → enforced by: the real run (DEMO 5) fails on a bad id; agent-builder verifies before pinning.
- **C-LLM-ACCESSOR** · MUST · The runtime LLM is reached via LangChain `init_chat_model` behind a thin
  `agent/llm.py` accessor (`get_model()`); no bespoke client, no SDK calls inside nodes.
  → enforced by: `agent/llm.py` recipe + a grep/reviewer check that nodes import the accessor (DEMO 2).
- **C-RUNNER-PREFIX** · SHOULD · Every README command is prefixed with its runner (`uv run …`) and runs from
  repo root.
  → enforced by: `demo_gate.sh` check 0 asserts a README exists and documents the `make gate` entry point
  (the owner-facing command); the gate proves the Makefile targets those commands wrap (`make gate` = DEMO
  1–8), not the README prose verbatim. README runner-prefix discipline is reviewer-checked.

---

## Changelog

- **1.0.0** (2026-06-20) — Initial constitution. Recovered the lost "works every time" MUST set from the
  pre-redo `spec/engineering/` archaeology (`reports/archaeology/SPEC-RECONCILIATION.md`) and bound each rule
  to a mechanical owner. Added `C-EARS-EVAL-BOUND` (the `[@eval]` token + lint) from the competitive critique
  (`reports/archaeology/COMPETITIVE-RESEARCH.md`) as our core differentiator.
