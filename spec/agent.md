# Agent

> Part 3 of the 4-part spec contract (see `harness/harness.md`). Decides which of the 11 agentic layers are
> ON. Baseline layers ship in Phase 1. The earns-its-place layers stay OFF until a capability needs them.
> Each layer names its recipe in `harness/patterns/`; the "why" is one line, specific to **this** agent.

## Layers

### Baseline — ON in Phase 1

- [x] **L1 · Model & providers** — `harness/patterns/model-and-providers.md`
  Runtime LLM behind `init_chat_model`; provider/model pinned in `spec/tech-stack.md` (cheap tier).
  *Why:* Gemini 2.5 Flash (`google_genai`) generates SQL + narrates grounded answers; no JSON-mode/vision needs.
- [x] **L2 · Context engineering** — `harness/patterns/context-engineering.md`
  Assemble the window each turn: domain system prompt + goal + tool results, within a token budget.
  *Why:* domain prompt + the dataset schema (fetched JIT via `get_schema`, not stuffed) must always be in context; raw query result sets are pruned/capped; **prior conversation turns (goal, answer) are reconstructed into the window** for multi-turn follow-ups (`converse-multiturn`).
- [x] **L3 · Memory (working / short-term)** — `harness/patterns/memory.md`
  In-run scratchpad + message history. Long-term / cross-run semantic memory is OFF (below).
  *Why:* within a run the agent tracks the schema it read, the SQL it ran, and intermediate results.
- [x] **L4 · Tools (in-process)** — `harness/patterns/tools-and-mcp.md`
  Internal actions = plain typed `@tool` in-process; MCP only for external integrations.
  *Why:* `get_schema`, `run_sql` (read-only DuckDB), `create_chart` (Vega-Lite), `write_todos`, `finish` — all own-process; nothing external.
- [x] **Orchestration · ReAct Deep-Agent loop** — `harness/patterns/react-agent.md`
  LangGraph `StateGraph`: `agent → (tools → agent)* → finalize`, with planning todos + a `finish` tool.
  *Why:* default loop; `write_todos` plans multi-step analyses; iteration cap + force_finalize guard runaway query loops.
- [x] **L7 · Guardrails (action-safety only)** — `harness/patterns/guardrails-and-hitl.md`
  Validate tool inputs, refuse out-of-scope/unsafe actions. HITL pause is OFF (below).
  *Why:* `run_sql` / `create_chart` are gated to **read-only** — any `INSERT/UPDATE/DELETE/DDL/COPY/ATTACH/PRAGMA-write` is refused; queries are row- and time-capped.
- [x] **L9 · Observability & Evals** — `harness/patterns/observability-and-evals.md`
  OTel-GenAI spans → SQLite → `/traces`; outcome + trajectory evals from the EARS criteria.
  *Why:* outcome eval on `query-data` (answer grounded in the SQL result, not invented) is the demo gate; every `chat`/`execute_tool.run_sql` step is a span.
- [x] **L10 · Interface / serving** — `harness/patterns/interface.md`
  Async FastAPI: `GET /health`, `POST /runs`, `GET /traces`. Port 8001.
  *Why:* plus dataset/upload + conversation endpoints and a Next.js chat UI (upload → ask → answer + chart → trace link); charts returned in the `POST /runs` envelope.
- [x] **L11 · Deploy & Operate** — `harness/patterns/deploy.md`
  Portable artifact (`langgraph.json` / Dockerfile); local SQLite → Postgres (+ checkpointer) on the prod ladder.
  *Why:* host TBD; productionised via `/deploy` (Phase 4) after the demo gate is green.

> Persistence (the data spine — `harness/patterns/persistence.md`) is always on. Async SQLAlchemy 2.0,
> SQLite (`aiosqlite`) local → Postgres (`asyncpg`) prod. Core tables `runs`/`messages`/`spans` + the domain
> tables below. The user's tabular data lives in **DuckDB** (analytical store), queried read-only by the agent.

### Earns its place

- [ ] **L5 · Retrieval / RAG** — `harness/patterns/retrieval.md`  → **OFF**
  *Why OFF:* grounding is via **live SQL** over the dataset, not semantic retrieval over a corpus; the schema is small enough to pass into context directly.
- [ ] **L3+ · Long-term / cross-run memory** — `harness/patterns/memory.md`  → **OFF**
  *Why OFF:* no facts persist across separate conversations/users; within-conversation continuity is handled by the checkpointer (L8), not a semantic memory store.
- [ ] **L6 · Multi-agent (supervisor + sub-agents)** — `harness/patterns/multi-agent.md`  → **OFF**
  *Why OFF:* one ReAct loop (introspect → query → answer/chart) holds the whole task; no distinct sub-tasks needing isolated context.
- [ ] **L7+ · HITL (human-in-the-loop pause)** — `harness/patterns/guardrails-and-hitl.md`  → **OFF**
  *Why OFF:* the agent is strictly read-only; there is no irreversible/external action to pause for. Writes are refused, not escalated.
- [ ] **L8 · Durability (checkpointer)** — `harness/patterns/durability.md`  → **OFF**
  *Why OFF:* multi-turn (`converse-multiturn`) is delivered by **conversation-history reconstruction** (L2 + persistence), not a checkpointer. This codebase uses a plain `messages` list with **no `add_messages` reducer** (`react-agent.md` warns against it); a LangGraph checkpointer assumes accumulating state, so wiring one would fight the design and be redundant with the persisted `messages`/`conversation_turns` rows. Instead `run_agent(goal, conversation_id)` loads prior turns' (goal, answer) and seeds them into the initial window. (Crash-resume — the actual L8 job — isn't needed: runs are short and in-process.)

## Domain tables (beyond runs/messages/spans)
- `datasets` — a named collection of uploaded files (id, name, created_at).
- `data_tables` — one per uploaded file: dataset_id, duckdb table name, original filename, row/column counts, column schema (JSON).
- `conversations` — a multi-turn thread bound to a dataset (id, dataset_id, title, created_at).
- `conversation_turns` — links each `runs` row to a conversation in order (conversation_id, run_id, idx).
- `charts` — a persisted Vega-Lite spec (with embedded data) tied to the run that produced it (run_id, title, spec JSON).
- (Analytical data itself is **not** a SQLite table — it lives in a per-dataset **DuckDB** store the agent queries read-only.)

## Notes
- The v1 feature set ships together (ingest + query + **charts** + **multi-turn**) — no deferral. Charts are
  collected per-run and returned in the `POST /runs` envelope; conversations link `runs` into a thread via
  `conversation_turns`, reconstructed into context on each new turn.
- Read-only enforcement is two-layered: a DuckDB connection opened `read_only=True` **and** a statement
  allowlist, so a write can't fire even from a force-finalize or a malformed model output.
