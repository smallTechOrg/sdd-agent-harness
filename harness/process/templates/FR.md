# FR-NNN — [Title]

**Date:** YYYY-MM-DD  
**Author:** [human / researcher]  
**Status:** draft | proposed | approved | in-progress | done

> **`proposed`** = scope deliberately split out of a core FR to keep the first delivery
> *lovable, not bloated*. A `proposed` FR is fully drafted now but does **not** enter the build
> pipeline; the user approves it (→ `approved`) **after** testing the core app, when its value is
> concrete. This is the *only* sanctioned way to defer scope — a real numbered FR with EARS
> criteria, human-approved later. It is not "drop it to a mythical later iteration" (still
> forbidden — see [planner.md](../agents/planner.md)).

> **Conventions for this file**
> - **Success Criteria use EARS** (Easy Approach to Requirements Syntax) — see the legend
>   below. Each criterion is one testable sentence the reviewer turns 1:1 into an
>   acceptance test.
> - **Write `[NEEDS CLARIFICATION: question]` inline** wherever you would otherwise guess.
>   Never silently invent a requirement. The supervisor resolves all markers in one bounded
>   clarify pass before the planner starts; resolved answers land in *Open Questions*.

---

## Problem Statement

> What pain, gap, or opportunity does this address? Who feels it and when?

<!-- One focused paragraph. No solution yet. -->

## Target Users

> Who will use this feature directly? What do they care about most?

| User | Context | Primary need |
|------|---------|--------------|
| | | |

## Success Criteria (EARS)

> How do we know this is done? Each line is **observable and testable**. Use one EARS form:
>
> - **Ubiquitous:** The `<system>` SHALL `<response>`.
> - **Event:** WHEN `<trigger>` the `<system>` SHALL `<response>`.
> - **State:** WHILE `<state>` the `<system>` SHALL `<response>`.
> - **Unwanted:** IF `<trigger>` THEN the `<system>` SHALL `<response>`.
> - **Optional:** WHERE `<feature is present>` the `<system>` SHALL `<response>`.

- [ ] <!-- WHEN a user uploads a CSV the system SHALL register it as a named dataset queryable within the same request. -->
- [ ] <!-- WHEN a user asks "show top 10 rows of <dataset>" the system SHALL return a Markdown table rendered as an HTML table in the web UI. -->
- [ ] <!-- IF the LLM provider is set to stub THEN the system SHALL pass the full unit suite with no API key and no network call. -->
- [ ] <!-- The system SHALL log every SQL execution to an audit_log row (timestamp, session_id, query_text, rows_affected, duration_ms). -->

## Non-Goals

> What is explicitly out of scope for this FR? The 30-minute ceiling is hard — anything that
> would push the build past it is split out here. **No idea gets dropped:** concrete excess goes
> to a numbered `proposed` FR; directional excess goes to `spec/ROADMAP.md`. Name the
> destination — a vague "later" is not acceptable.

- <!-- Concrete excess → "Multi-chart dashboards → FR-002 (proposed)" -->
- <!-- Directional excess → "Real-time collaboration → spec/ROADMAP.md" -->
- <!-- Out-of-scope by design → "Authentication — not required for this milestone" -->

## Key Constraints

> Hard limits that cannot be negotiated away.

| Constraint | Value | Reason |
|-----------|-------|--------|
| Stack | <!-- e.g. Python + FastAPI + LangGraph + DuckDB --> | <!-- why --> |
| Database | <!-- e.g. DuckDB (analytics) / SQLite (relational) — local-first --> | <!-- why --> |
| Deploy target | <!-- e.g. local demo, then Render on request --> | <!-- why --> |
| API keys needed | <!-- list, e.g. GEMINI_API_KEY --> | <!-- when needed --> |
| Timeline | <!-- if any --> | <!-- why --> |

## Open Questions — clarification ledger

> Every `[NEEDS CLARIFICATION]` marker raised above is resolved here in the one clarify
> pass. Format: question → decision → who decided. An FR is not `approved` while any marker
> is unresolved.

- [ ] <!-- question + the resolved decision + who resolved it -->

## Golden Path Demo Script

> Numbered walkthrough of what a 2-minute product demo looks like. Written in user terms, not
> API terms. This is the primary acceptance test — the supervisor runs it on the delivered build.
> If any step requires the demonstrator to explain why something looks unfinished, quality has
> not been met. The researcher writes this; the reviewer runs it.

1. <!-- e.g. Open the app — stub-mode banner is visible across the top -->
2. <!-- e.g. Upload "sales.csv" — dataset appears in the sidebar with row count -->
3. <!-- e.g. Ask a question — Markdown table renders + chart below it -->

## Step Plan

> **The FR is the single trackable file.** The planner writes this DAG once the spec is
> signed off. Every stage reads it to know what to build next and updates its step row as
> control passes back to the supervisor. This file is how parallel sub-agents coordinate —
> it is the one artefact everyone writes to and reads from. The session report holds the
> execution log; this file holds the execution plan.

| # | Deliverable | Depends on | Parallel group | Gate command | Est. |
|---|-------------|-----------|----------------|-------------|------|
| 0 | scaffold — /health green | — | — | `curl :8001/health` | ~8m |
| 1 | <!-- --> | 0 | A | `uv run pytest` | ~12m |

## Progress Tracker

> **Everyone updates their row on handoff.** Status: `todo → in-progress → gate-green → accepted`.
> `accepted` only when the user accepts the whole at the iteration boundary. The analyser
> cross-checks this against gate output in the session report — a `gate-green` row with no
> matching output is drift. Reading this table alone tells anyone where the build stands.

| Step | Status | Gate output (session ref) | Reviewer sign-off | Dominant cost |
|------|--------|--------------------------|-------------------|---------------|
| 0 | todo | — | — | — |
