---
description: Turn a one-line idea into a working, demo-gated production agent — intake, spec, plan, generate from harness/patterns, demo gate.
argument-hint: "<idea>"
---

# Workflow: /build

Turn a one-line idea into a working, demo-gated agent. This is the procedure; the rules are
`harness/harness.md` (the law) and the sequencing is `agents/agent-builder.md` — read both; this file
does not restate them. Sub-agents share no memory: pass every intake answer to each explicitly.

```
/build "<idea>"  →  intake (one round, ≤4 Qs upfront)  →  spec-writer + tech-designer + planner
                 →  analyze pre-flight (mechanical, inline)  →  SINGLE approval (scope+stack+plan, AskUserQuestion)
                 →  generate from harness/patterns  →  demo gate (run→read→fix→re-run loop)  →  running
```

There is **exactly one** human checkpoint: the single approval of scope + stack + plan, after the spec/plan
draft + pre-flight and **before** any code is generated, presented via `AskUserQuestion` (C-ASKUSER,
`agents/agent-builder.md` § Lifecycle 2). Intake's Q4 already collected the API key, so after this one
approval the build runs **unattended** to the green gate — no key prompt later, no mid-build "Proceed?"
(C-UNATTENDED, user memory). "Unattended" means *after the approval*; it is not a contradiction.

**What "done" means here, and what we promise the user.** `/build` does not hand back a document — it
hands back an agent that **booted and gave the right answer, proven by a gate that exits 0**. Lead with
that proof. Be honest about the two zones it spans (`SPEC-RECONCILIATION.md` § F):

- a **reused, version-pinned TESTED CORE** (server, ReAct loop, config, envelope, persistence, traces,
  the gate harness, the UI shell) — *code is the source of truth there, like any framework dependency*;
- a **GENERATED DOMAIN** (capability nodes, tools, prompts, EARS evals, domain UI screens) — *the spec
  is the source of truth there.* `/build` fills only the domain seams; it does not regenerate the core.

Do not tell the user "the spec authored everything." Tell them: the core is proven once and reused; the
spec drives the domain; **every acceptance criterion is bound to an executable check** and the gate
proves the agent ran.

After intake, run to the demo gate without pausing (`agent-builder.md` § Autonomy). Pause only on a
true blocker — then ask via the dynamic question UI, never guess.

---

## 1. Intake — one round, ≤4 questions

**Load `AskUserQuestion` first.** It is a deferred tool — run `ToolSearch` with
`select:AskUserQuestion` (or search `"ask user question"`) to fetch its schema BEFORE intake, then use
it for every question and for the (rare) blocker prompt. A text-only "Proceed?" is never acceptable
(`harness.md`; user memory). One pass through it; ask all four at once; do not drip-feed. The idea may
already answer Q1 — still confirm it. The answers seed the spec, so capture them verbatim.

| # | Question | Options (pick or free-type) | Feeds |
|---|----------|-----------------------------|-------|
| 1 | **What should the agent do?** (idea + domain) | free text | `spec/product.md` |
| 2 | **What tools + data does it need?** | key-free / local (no creds; e.g. compute, a bundled corpus) · a data source (DB, files, API you own) · a **key-bearing 3rd-party HTTP API** (web search, a vendor REST API with a static API key → an in-process `@tool` reading an `APP_`-prefixed `SecretStr`) · an external integration via MCP (OAuth SaaS only) | `spec/tech-stack.md` tools, `spec/agent.md` |
| 3 | **How is it used?** | **UI** (built-in `/traces` + a minimal run page, default) · API only · CLI · scheduled/cron | `spec/tech-stack.md`, `interface` layer |
| 4 | **Provider + API key + runtime model?** | provider (anthropic / openai / google) · **API key (required)** · runtime model (cheap tier default) | `spec/tech-stack.md`, `agent/config.py` |

Defaults when the user has no preference: interface = built-in UI; runtime model = the cheap tier for the
chosen provider (`claude-haiku-4-5-20251001` / `gpt-5-nano` class / `gemini-2.5-flash` — verify the id
against the provider before pinning, per `harness.md`). The tool answer maps straight onto the 3-layer
model in `patterns/tools-and-mcp.md`: in-process `@tool` for own logic/data **and for a static-key
third-party HTTP API** (the key is an `APP_`-prefixed `SecretStr` in `config.py`, never sent to the model);
MCP is reserved for **OAuth 2.1 SaaS integrations only** (it forbids static secrets), so a web-search /
vendor-REST API with an API key is an in-process async `@tool`, not MCP.

**Collect the API key here (Q4) — the build runs unattended to the green gate.**
If the user skips it, ask once before generating code. Never pause mid-build for it.

The only sanctioned second question round is the analyze pre-flight (§2a) surfacing an unresolved
`[NEEDS CLARIFICATION]` — ask it upfront via `AskUserQuestion`, resolve it, then proceed to the single
approval (§2). After that approval there are **no further pauses** — no mid-build "Proceed?", no key prompt
(user memory). The lone approval is the spec/plan sign-off below; the build is unattended thereafter.

## 2. Draft the spec + plan (no code yet)

With the four answers, fan out (`agent-builder.md` § Draft):

- **spec-writer** fills `spec/product.md` (what / success criteria / domain / out-of-scope) and one
  `spec/capabilities/<name>.md` per capability — each criterion as an EARS line
  *"WHEN `<trigger>` the system SHALL `<response>`"*, and **every EARS line carries an `[@eval: …]`
  token** binding it to its executable check. This token is the differentiator (`COMPETITIVE-RESEARCH.md`
  §5): the criterion is not "documented," it is *bound* to a check that the gate runs. Shape:

  ```markdown
  - WHEN asked about refund timing the system SHALL state 5 business days.
    [@eval: tests/test_refunds_gate.py::test_refund_timing]
  ```

  The agent fills the token; **the non-coder never sees it** — it surfaces only as the gate's pass/fail
  line. Stories are **prioritised P1/P2/P3** so the v1 slice is an explicit choice, not an accident
  (`COMPETITIVE-RESEARCH.md` §2.6): P1 is the one real capability; P2/P3 are spec-registered, deterministic,
  journey-complete **stubs** (`SPEC-RECONCILIATION.md` decision #2/#3) — never silent gaps.
- **tech-designer** fills `spec/tech-stack.md` (provider, runtime model, DB = local-first
  `sqlite+aiosqlite`, deploy target, tools) and marks layers in `spec/agent.md` — default baseline ON:
  ReAct Deep-Agent, in-process tools (+ MCP if Q2 = external), memory, observability, evals; everything
  else OFF until a capability needs it (`planner.md` § How to order).
- **planner** writes `reports/implementation-plan.md` (`planner.md` shape): Phase 1 = walking skeleton +
  the **P1** capability real + P2/P3 as deterministic stubs, tagged `[tier: demo]`.
- **spec-reviewer** + **plan-reviewer** validate in the background — advisory only; the gate is mechanical.

Every layer marked ON must trace to a capability; no speculative layers (`agent.md` is the on/off ledger).

## 2a. The analyze pre-flight — mechanical, BEFORE any code

Catch drift *before* generation, when it is cheap (`COMPETITIVE-RESEARCH.md` §2.4). This is an **inline
checklist the agent runs inside `/build`** (not a separate slash command), against the drafted spec; **every
line is a hard pass/fail**, and any failure stops the build until the spec is fixed — no code is written
against a spec that fails pre-flight.

| # | Pre-flight check | Fails when |
|---|------------------|-----------|
| 1 | **Every success criterion → ≥1 capability** | a `spec/product.md` success criterion maps to no `spec/capabilities/*.md` |
| 2 | **Every capability's layer is ON** | a capability needs a layer (retrieval, memory, MCP…) that `spec/agent.md` leaves OFF |
| 3 | **Every tool has a tech-stack home** | a tool a capability calls is absent from `spec/tech-stack.md` |
| 4 | **Every EARS line has a well-formed, unique `[@eval]`** | a `WHEN … SHALL …` line has no `[@eval:]` token, the token isn't `path::case`-shaped, or two lines share one case — run `python -m agent.eval_lint --preflight` (presence + shape + uniqueness only; the **existence** check is deferred to the post-generation gate, DEMO 1, since no test file exists yet) |
| 5 | **No unresolved `[NEEDS CLARIFICATION]`** | any such marker remains in the spec — this **blocks generation** |
| 6 | **Exactly one P1; P2/P3 are stubs** | zero or many P1 capabilities, or a non-P1 marked as a real build target |

On a check-1/2/3/6 failure the agent self-corrects the spec and re-runs the pre-flight (it is a loop, like
the gate). On check-4 it adds the missing/ill-formed token (preflight validates presence + shape +
uniqueness; the gate later proves the token's `path::case` actually resolves — `workflows/gates.md`). On check-5 — an unresolved `[NEEDS CLARIFICATION]` — it
asks the user one focused question via `AskUserQuestion` (this is the legitimate second intake round, all
questions upfront), resolves it, then proceeds. The build never generates code against a spec that still
fails pre-flight. This is the honest version of "spec-driven": the spec must be internally consistent and
fully bound to checks before a single line is written.

## 2b. The single approval — scope + stack + plan (the one human checkpoint)

Pre-flight green, present scope + stack + plan for the **single approval** via `AskUserQuestion` (never a
text-only "Proceed?" — C-ASKUSER, user memory). This is the lone checkpoint and it sits **here**: after the
spec/plan draft + pre-flight, before §3 generation. It is the one moment a human can catch a wrong spec
before a green gate certifies it (`COMPETITIVE-RESEARCH.md` §4). On approval the build runs unattended to the
green gate (C-UNATTENDED); on a change request, fold it into the spec, re-run pre-flight, re-present.

## 3. Generate code fresh — on `feature/<slug>-<date>`

**Activate the git hooks first, then branch** — the hooks are the local owners of `C-SECRET-TYPE`,
`C-BRANCH-PR`, and `C-NO-ADD-ALL`, and `core.hooksPath` is unset on a fresh clone, so without this step
nothing enforces them (`.githooks/pre-commit`). `<slug>` = the product slug, `<date>` = `YYYY-MM-DD`.

```bash
git config core.hooksPath .githooks               # enable the branch-guard + add-all + secret-scan hook
git switch -c "feature/<slug>-$(date +%Y-%m-%d)"  # main is boilerplate-only; the hook blocks app code on it
```

Generate from the recipes in `harness/patterns/` for **only the layers `spec/agent.md` marks ON** — copy
the proven blocks, fill the spec's domain specifics, **pin current library versions** (verify latest on
PyPI before pinning; a guessed/old version 404s — `harness.md`). The recipes in `harness/patterns/` carry the
proven, copyable code — generate from them. The Phase-1 spine (the walking skeleton from `planner.md`):

| Module | Recipe | Carries |
|--------|--------|---------|
| `agent/config.py` | `patterns/model-and-providers.md` | `get_settings()` (cached `Settings`, env prefix `APP_`, cheap runtime model) |
| `agent/db.py` | `patterns/persistence.md` | async SQLAlchemy 2.0; `Run` / `Message` / `Span`; `get_sessionmaker()` + `init_db()` |
| `agent/observability.py` | `patterns/observability-and-evals.md` | `span()` ctx mgr → `Span` rows (OTel GenAI names) |
| `agent/llm.py` | `patterns/model-and-providers.md` | `get_model()` (raises without `APP_LLM_API_KEY`) |
| `agent/tools.py` | `patterns/tools-and-mcp.md` | `@tool`s incl. `write_todos`, `finish`; `TOOLS`/`TOOL_MAP` |
| `agent/state.py` · `graph.py` | `patterns/react-agent.md` | `AgentState`; `build_graph()` (agent↔tools, finalize) |
| `agent/runner.py` | `patterns/react-agent.md` | `run_agent()` — span `invoke_agent`, persist run+messages |
| `agent/server.py` | `patterns/interface.md` | FastAPI: `/health`, `POST /runs`, `/traces` viewer |
| `agent/__init__.py` · `agent/__main__.py` | `patterns/interface.md` | package marker; `python -m agent` → uvicorn on `settings.port` (gate check 3 boots this) |
| `agent/evals.py` | `patterns/observability-and-evals.md` | `outcome_eval` / `stable_outcome_eval` / `trajectory_eval` (imported by the suite + `gate_eval`) |
| `agent/eval_lint.py` | `workflows/gates.md` | the `[@eval]` binding lint — gate check 1, run as `python -m agent.eval_lint` |
| `agent/gate_eval.py` | `workflows/gates.md` | judge-stable outcome+trajectory CLI — gate check 6, run as `python -m agent.gate_eval` |
| `agent/sessions.py` *(generate whenever a resource — a pasted document, transcript, CSV, file, or built index — is loaded once and reused across follow-up turns, regardless of size/cost)* | `patterns/persistence.md` | session-scoped live-resource store + `current_session_id` ContextVar + `load_resource` HTTP ingest seam — **REQUIRED by `C-SESSION-SCOPE`** for any "analyze an uploaded/pasted X" / multi-turn-over-a-loaded-resource agent (a meeting transcript is a cheap string but still needs cross-turn reuse — don't skip because it isn't "heavy"); without it Q2 loses the resource (`SESSION_DATA_LOST`) and the data-agent gate fails Q1 |
| `agent/guardrails.py` *(generate when a tool executes code/SQL)* | `patterns/guardrails-and-hitl.md` | AST-validated `safe_eval` (never regex dispatch) — **REQUIRED by `C-ACTION-SAFETY`** for any code/SQL-executing tool; an ungated code tool is an injection surface and fails the trajectory contract |

The five gate-support modules (`evals.py`, `eval_lint.py`, `gate_eval.py` + the server/main they run against)
are NOT optional — `make gate` runs every one of them (`workflows/gates.md` checks 1/2/3/6); a clean `agent/`
tree without them dies at gate step 1 with `ModuleNotFoundError`. The two *italicised* rows
(`sessions.py`, `guardrails.py`) are **conditional but mandatory once their trigger holds** — they are OFF by
default, but a capability that ingests a resource (`C-SESSION-SCOPE`) or executes code/SQL (`C-ACTION-SAFETY`)
**must** generate them; the analyze pre-flight's layer check (§2a) catches a capability that needs one but
left it OFF. Alongside the package, generate the **top-level project files the gate and deploy both require**:

| File | Recipe | Carries |
|------|--------|---------|
| `pyproject.toml` | `workflows/gates.md`, `patterns/*` | project metadata + **pinned** deps + `[tool.pytest.ini_options]` with **both** `asyncio_mode = "auto"` **and** `pythonpath = ["."]`. **"Pin current versions" means pin them HERE.** `pythonpath = ["."]` lets shared test helpers be imported absolutely (`from tests.helpers import …`) so collection doesn't fail. `uv run pytest`, `make gate`, and deploy's `langgraph.json "dependencies":["."]` all need this file to exist. |
| `Makefile` | `workflows/gates.md` | the `gate` / `demo-gate` targets (checks 1–8) — the entry point `/build` invokes |
| `scripts/demo_gate.sh` | `workflows/gates.md` | gate checks 3–8 (boot, health, two-turn, judge, UI, traces) |
| `tests/__init__.py` · `tests/e2e/__init__.py` | — | empty package markers. Without them, shared-helper imports across test files (`from tests.helpers import …`, `patterns/observability-and-evals.md`) raise `ImportError: attempted relative import with no known parent package` and `uv run pytest` dies at **collection** — gate check 2 never starts, with an opaque error a non-tech user can't decode. |
| `tests/conftest.py` | `patterns/persistence.md` | the autouse create_all/drop_all-per-test async DB fixture |
| `tests/test_eval_lint.py` | `workflows/gates.md` | one-line `assert agent.eval_lint.main() == 0` so the binding is enforced under a bare `pytest` too |

Without `asyncio_mode = "auto"` in `pyproject.toml`, pytest-asyncio's default strict mode **silently skips
every unmarked `async def test_*`** — including `test_demo_gate` (the in-process 200-with-wrong-answer guard)
and the autouse async DB fixture — while the suite still reports green. That is a false-green in the very
check the harness leans on, so this line is mandatory, not optional (`patterns/observability-and-evals.md`).

**`config.py` and `runner.py` are load-bearing — there is ONE canonical copy of each, and it lives in the
recipe, not here.** Do not paste a second copy into this file (a divergent paste is how
`C-SECRET-TYPE`/`C-ENV-STRIP`/the `price_*` + `validate_required_config` contracts silently drift):

- **`agent/config.py`** → copy verbatim from `patterns/model-and-providers.md` § *Code — `agent/config.py`*.
  It carries the non-negotiables a stripped-down copy would drop: `llm_api_key: SecretStr` (`C-SECRET-TYPE`),
  the inline-`#`-comment strip validators (`C-ENV-STRIP`), `extra="ignore"` (`C-ENV-IGNORE`),
  `price_in`/`price_out` (read by `runner.py` for the `cost_usd` column), and `validate_required_config()`
  (called by `server.py`'s lifespan — `patterns/interface.md`). Omitting any of these yields an
  `AttributeError`/`ImportError` at runtime or a key that 401s on the real run while the build is green.
- **`agent/runner.py`** → copy verbatim from `patterns/interface.md` § *Code — `agent/runner.py`*. It carries
  `session_id`/`thread_id` + the checkpointer (short-term memory, the two-turn gate), the per-run token→cost
  rollup into `runs.cost_usd`, the `status:"completed"` field the gate reads off the `ok()` envelope, and the
  `current_session_id` ContextVar set around `graph.ainvoke` so a session-resource query tool finds the active
  session WITHOUT the model supplying it (`C-SESSION-SCOPE` read path — `patterns/persistence.md`). The loop
  does NOT inject session context into tools, so omitting this line makes the query tool always report "no data
  loaded" — a green gate, a broken data agent.

These two files are the single source of truth; this workflow references them so the two never diverge.

Build only what the spec needs — no gold-plating (`agent-builder.md`).

## 4. Demo-tier gate — run → read → fix → re-run until green

**Done = the gate exits 0**, never prose. The gate is the loop's exit condition, not a one-shot
checkpoint: run it, read the failure, fix the cause, re-run. The full check list and the exact script
live in `workflows/gates.md` — this is the one-line entry:

```bash
make gate          # the whole DEMO suite; echo $? — 0 is the only pass (workflows/gates.md)
```

What that script proves (do not weaken any of these — see `workflows/gates.md` for the full table):
server boots over real HTTP, `/health` 200, a real **TWO-TURN** run (Q1 then a follow-up Q2 on the same
session — **any Q2 error fails the gate**), the **outcome eval passes with judge-stability** (a 200 with
a wrong answer fails; the judge is multi-sampled so exit-0 is deterministic, not probabilistic), the
`[@eval]` lint (every EARS line resolves to a real check), the deterministic test pyramid **and** a
Playwright UI E2E (post-JS DOM, no console error), and `/traces` renders the run's spans.

**When a step fails — self-diagnose, don't pause.** Read the actual error, trace it to the source file,
read the failing span at `/traces`, fix the cause, re-run the gate from that step. The only external
blocker is an unfunded/missing key — everything else is diagnosable from logs + `/traces`, so resolve it
yourself. qa-auditor confirms the exit code; "should pass" is never a pass (`harness.md` § honest).

**After the gate passes**, leave the server running and tell the user how to reach it:
- Backend: `http://localhost:8001` · Traces: `http://localhost:8001/traces`
- UI (if built): `cd ui && npm run dev` → `http://localhost:3001`

The user must be able to test immediately — do not kill the server.

Maintain/extend via `/spec-new-capability`; productionise via `/deploy` when the user asks.

## On a true blocker

An external blocker (missing/unfunded key, a spec ambiguity that stops code generation) stops the
loop. Emit a one-paragraph status — what works, what's blocked, the single fix needed — then ask
via `AskUserQuestion`. Resume to the gate once cleared. Do **not** fake a pass.
