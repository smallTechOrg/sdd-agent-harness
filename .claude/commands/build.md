---
description: Turn a one-line idea into a working, demo-gated production agent — intake, spec, plan, generate from harness/patterns, demo gate.
argument-hint: "<idea>"
---

<!-- GENERATED from harness/ — do not edit; run `python harness/generate.py` -->

# Workflow: /build

Turn a one-line idea into a working, demo-gated agent. This is the procedure; the rules are
`harness/harness.md` (the law) and the sequencing is `agents/agent-builder.md` — read both; this file
does not restate them. Sub-agents share no memory: pass every intake answer to each explicitly.

```
/build "<idea>"  →  intake (1 round)  →  spec-writer + tech-designer + planner  →  ONE approval
                 →  generate from harness/patterns on feature/<slug>-<date>  →  demo gate  →  running
```

After the one approval, run to the demo gate without pausing (`agent-builder.md` § Autonomy). Pause only
on a true blocker — then ask via the dynamic question UI, never guess.

---

## 1. Intake — one round, 4 questions

One pass through the dynamic question UI (`AskUserQuestion`). Ask all four at once; do not drip-feed.
The idea may already answer Q1 — still confirm it. The answers seed the spec, so capture them verbatim.

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

**A missing or unfunded API key is a true blocker.** No real run, no outcome eval, no green demo gate
without one (`harness.md`). Stop and ask; do not stub a fake key to proceed.

## 2. Draft the spec + plan (no code yet)

With the four answers, fan out (`agent-builder.md` § Draft):

- **spec-writer** fills `spec/product.md` (what / success criteria / domain / out-of-scope) and one
  `spec/capabilities/<name>.md` per capability — each criterion as an EARS line
  *"WHEN `<trigger>` the system SHALL `<response>`"* (these become the eval gate's inputs).
- **tech-designer** fills `spec/tech-stack.md` (provider, runtime model, DB = local-first
  `sqlite+aiosqlite`, deploy target, tools) and marks layers in `spec/agent.md` — default baseline ON:
  ReAct Deep-Agent, in-process tools (+ MCP if Q2 = external), memory, observability, evals; everything
  else OFF until a capability needs it (`planner.md` § How to order).
- **planner** writes `reports/implementation-plan.md` (`planner.md` shape): Phase 1 = walking skeleton +
  simplest capability, tagged `[tier: demo]`.
- **spec-reviewer** + **plan-reviewer** validate in the background — advisory only; the gate is mechanical.

Every layer marked ON must trace to a capability; no speculative layers (`agent.md` is the on/off ledger).

## 3. One approval

Present scope + stack + plan in a single message and get one confirm (`agent-builder.md` § One approval):

```
Building: <product, one line>
Capabilities: <list> · Layers ON: <from spec/agent.md>
Stack: <provider>/<runtime model> · <DB> · interface=<…> · tools=<in-process|MCP …>
Plan: Phase 1 <skeleton+capability> … Phase N productionise   (reports/implementation-plan.md)
Proceed? (one confirm — then I build to the demo gate autonomously)
```

No application code exists before this confirm. After it, autonomy is on.

## 4. Generate code fresh — on `feature/<slug>-<date>`

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

## 5. Demo-tier gate — the only proof of "done"

Run the gate (`workflows/gates.md`); **done = the gate script exits 0**, never prose (`harness.md`). The
demo tier asserts, in order: the package imports, tests pass (a `FakeModel` drives the ReAct loop with no
key — ≥2 iterations, tool spans recorded, `force_finalize` on runaway), the server boots, `GET /health`
→ 200, a **real** `POST /runs` completes against the funded key, the **outcome eval passes** (a 200 with a
wrong answer is a fail — the answer must satisfy the capability's EARS criteria), and spans are visible at
`/traces`. qa-auditor confirms the exit code (`agents/qa-auditor.md`).

```bash
python -m pytest -q                                   # FakeModel loop, no key needed
python -m agent &                                     # uvicorn on :8001 (agent/__main__.py)
until curl -sf localhost:8001/health; do sleep 1; done
curl -sf -X POST localhost:8001/runs -d '{"goal":"<a real success-criterion task>"}' \
     -H 'content-type: application/json'              # real run → outcome eval
# open localhost:8001/traces — timeline of runs + spans must render
```

Green gate → the agent is **running** and demo-complete. Maintain/extend via `/spec-new-capability`;
productionise via `/deploy` when the user asks (`workflows/deploy.md`).

## On a stall — partial-delivery report

If a true blocker stops the demo gate (missing/unfunded key, a red gate you cannot resolve, an ambiguous
spec), stop and emit a short report — do **not** fake a pass (`harness.md`, `qa-auditor.md`):

```
PARTIAL DELIVERY — <product>   branch: feature/<slug>-<date>
Works:    <green checks — e.g. imports, tests, /health, /traces>
Stubbed:  <what isn't real yet, and why>
Blocker:  <the one thing — e.g. APP_LLM_API_KEY unfunded → no real run / outcome eval>
Next fix: <the single action that unblocks the demo gate>
```

Then ask the one unblocking question via the dynamic question UI. Resume to the demo gate once cleared.
