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
                 →  /analyze pre-flight (mechanical)  →  generate from harness/patterns
                 →  demo gate (run→read→fix→re-run loop)  →  running
```

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
| 2 | **What tools + data does it need?** | key-free / local (no creds; e.g. compute, a bundled corpus) · a data source (DB, files, API you own) · an external integration via MCP (3rd-party SaaS) | `spec/tech-stack.md` tools, `spec/agent.md` |
| 3 | **How is it used?** | **UI** (built-in `/traces` + a minimal run page, default) · API only · CLI · scheduled/cron | `spec/tech-stack.md`, `interface` layer |
| 4 | **Provider + API key + runtime model?** | provider (anthropic / openai / google) · **API key (required)** · runtime model (cheap tier default) | `spec/tech-stack.md`, `agent/config.py` |

Defaults when the user has no preference: interface = built-in UI; runtime model = the cheap tier for the
chosen provider (`claude-haiku-4-5-20251001` / `gpt-5-nano` class / `gemini-2.5-flash` — verify the id
against the provider before pinning, per `harness.md`). The tool answer maps straight onto the 3-layer
model in `patterns/tools-and-mcp.md`: in-process `@tool` for own logic/data, MCP for external SaaS only.

**Collect the API key here (Q4) — the build runs unattended to the green gate.**
If the user skips it, ask once before generating code. Never pause mid-build for it.

The only sanctioned second question round is the `/analyze` pre-flight (§2a) surfacing an unresolved
`[NEEDS CLARIFICATION]` — ask it upfront via `AskUserQuestion`, resolve it, then build with no further
pauses. All questions in, then build — no gates in between, no mid-build "Proceed?" (user memory).

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

## 2a. `/analyze` pre-flight — mechanical, BEFORE any code

Catch drift *before* generation, when it is cheap (`COMPETITIVE-RESEARCH.md` §2.4). This is a checklist
the agent runs against the drafted spec; **every line is a hard pass/fail**, and any failure stops the
build until the spec is fixed — no code is written against a spec that fails pre-flight.

| # | Pre-flight check | Fails when |
|---|------------------|-----------|
| 1 | **Every success criterion → ≥1 capability** | a `spec/product.md` success criterion maps to no `spec/capabilities/*.md` |
| 2 | **Every capability's layer is ON** | a capability needs a layer (retrieval, memory, MCP…) that `spec/agent.md` leaves OFF |
| 3 | **Every tool has a tech-stack home** | a tool a capability calls is absent from `spec/tech-stack.md` |
| 4 | **Every EARS line has a resolvable `[@eval]`** | a `WHEN … SHALL …` line has no `[@eval:]` token, or the token points at a path the build won't create |
| 5 | **No unresolved `[NEEDS CLARIFICATION]`** | any such marker remains in the spec — this **blocks generation** |
| 6 | **Exactly one P1; P2/P3 are stubs** | zero or many P1 capabilities, or a non-P1 marked as a real build target |

On a check-1/2/3/6 failure the agent self-corrects the spec and re-runs the pre-flight (it is a loop, like
the gate). On check-4 it adds the missing token. On check-5 — an unresolved `[NEEDS CLARIFICATION]` — it
asks the user one focused question via `AskUserQuestion` (this is the legitimate second intake round, all
questions upfront), resolves it, then proceeds. The build never generates code against a spec that still
fails pre-flight. This is the honest version of "spec-driven": the spec must be internally consistent and
fully bound to checks before a single line is written.

## 3. Generate code fresh — on `feature/<slug>-<date>`

Branch first; hooks block app code on `main` (`harness.md`). `<slug>` = the product slug, `<date>` =
`YYYY-MM-DD`.

```bash
git switch -c "feature/<slug>-$(date +%Y-%m-%d)"
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

The fixed contract every build satisfies — `config.py` and `runner.py` are load-bearing, copy verbatim:

```python
# agent/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")
    llm_provider: str = "anthropic"
    llm_model: str = "claude-haiku-4-5-20251001"   # cheap runtime tier — verify id before pinning
    llm_api_key: str = ""                            # APP_LLM_API_KEY — required for a real run
    database_url: str = "sqlite+aiosqlite:///./agent.db"   # local-first; Postgres at /deploy
    port: int = 8001
    max_iterations: int = 6

@lru_cache
def get_settings() -> Settings:                      # cached singleton — every recipe imports this
    return Settings()
```

```python
# agent/runner.py — create Run, run the graph under a top span, persist messages + outcome
import uuid
from langchain_core.messages import SystemMessage, HumanMessage
from .config import get_settings
from .db import get_sessionmaker, Run, Message
from .graph import build_graph
from .llm import get_model
from .observability import span

DOMAIN_PROMPT = "..."  # spec/product.md § Domain instructions

async def run_agent(goal: str, model=None, run_id: str | None = None) -> dict:
    run_id = run_id or str(uuid.uuid4())
    model = model or get_model()
    graph = build_graph(model)
    async with get_sessionmaker()() as s:
        run = Run(id=run_id, goal=goal, status="running")
        s.add(run); await s.commit()
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content=goal)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }
    async with span(run_id, "invoke_agent", kind="INTERNAL", goal=goal):
        final = await graph.ainvoke(state, config={"recursion_limit": 50})
    async with get_sessionmaker()() as s:
        for m in final["messages"]:
            s.add(Message(id=str(uuid.uuid4()), run_id=run_id,
                          role=m.type, content=str(m.content)))
        run = await s.get(Run, run_id)
        run.status, run.answer, run.iterations = "completed", final.get("answer"), final["iterations"]
        await s.commit()
    return {"run_id": run_id, "answer": final.get("answer"),
            "iterations": final["iterations"], "messages": final["messages"]}
```

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
