# Usage-specs — version-pinned API shapes the seam-generating agent reads first

A **usage-spec** is a tiny, version-**stamped** cheat-sheet for one pinned library: the *correct* and
*forbidden* API shapes plus the 2–3 idioms our tested core actually relies on for **that** version. It is
the right-sized version of Tessl's "Spec Registry" idea (`reports/archaeology/COMPETITIVE-RESEARCH.md` §2):
the one move that hardens the one surface we still generate — the **domain seams** Claude Code writes in
`agent/` from the layer recipes. A model trained across many library versions hallucinates a plausible-but-
wrong API; these files pin the agent to the API of the version we actually install.

## How they're used (build-time)
Before generating the domain seams for a layer, the **agent-builder reads the usage-spec(s) for the libs that
layer touches** (`agents/agent-builder.md` § Generate, step 3), then writes code from the layer recipe.
A usage-spec does **not** replace the recipe in `harness/patterns/*.md` (the recipe is the proven code); it
is the *API-shape guardrail* that stops a generated seam from drifting onto a wrong-version call.

Map of which spec covers what:

| Usage-spec | Pinned libs | Recipes it guards |
|---|---|---|
| `fastapi.md` | `fastapi`, `uvicorn` | `interface.md` (server, `/health`, `/runs`, `/traces`, SSE) |
| `langgraph.md` | `langgraph` | `react-agent.md`, `durability.md`, `guardrails-and-hitl.md` |
| `langchain-core.md` | `langchain`, `langchain-core`, provider pkg | `model-and-providers.md`, `tools-and-mcp.md`, `context-engineering.md` |
| `sqlalchemy-async.md` | `sqlalchemy`, `aiosqlite`, `asyncpg` | `persistence.md`, `observability-and-evals.md`, `memory.md` |
| `pydantic-settings.md` | `pydantic`, `pydantic-settings` | `model-and-providers.md` (`config.py`) |
| `nextjs.md` | `next`, `react` | `interface.md` (the web UI shell + `/traces` deep-link) |

## The version-pin rule (READ THIS)
Each file carries a **`Version:` stamp** at the top — the version it describes. The stamp is a contract:

> **A library version bump MUST refresh its usage-spec in the same change.** A *stale* usage-spec is **worse
> than none** — it teaches the wrong API with false authority, and the agent trusts it over its own training.

So:
- When you (or the build) bump a pinned lib past the stamp, **re-derive that usage-spec against the new
  version's docs** and update the stamp + date. The drift-auditor flags a lockfile/`agent/` version that no
  longer matches a usage-spec stamp (`agents/drift-auditor.md`) precisely so this never silently rots.
- These stamps are **mid-2026** snapshots. **Always verify the current version at build time** before pinning
  (the same "a guessed/old version 404s" rule the recipes state) — if it moved, refresh the file first.
- Keep each file *short*: the forbidden shapes + the few idioms our core relies on, nothing encyclopedic.
  Encyclopedic = stale fast = worse than none.

> ⚠️ **Major-version watch (mid-2026):** LangChain **and** LangGraph reached **v1.0** and moved on to the
> 1.x line. v1 changed several import paths and the agent-construction surface from the 0.x examples that
> dominate model training data — exactly the hallucination these files exist to stop. Treat the
> `langchain-core.md` and `langgraph.md` v1 caveats as load-bearing.
