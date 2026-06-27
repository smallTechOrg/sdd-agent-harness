# Agent

The CSV-analysis agent runs as a LangGraph `StateGraph` (extending the skeleton's compiled graph in `src/graph/agent.py`). The graph answers ONE question per run, and its central job is to enforce the privacy boundary: only the question + the locally-derived profile ever reach the LLM prompt.

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges — chosen |

**Chosen:** a small **LangGraph linear pipeline with an error branch** (load → build prompt → call LLM → finalize, with a shared `handle_error` sink). No tool-use loop and no multi-agent routing is needed in Phase 1: the flow is deterministic and there is exactly one LLM call. (See [`harness/patterns/agentic-ai.md`](../harness/patterns/agentic-ai.md) — this is the lightweight end of the catalogue, justified because the only "tools" are local pandas functions invoked deterministically, not LLM-selected.)

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `answer` | Gemini | `gemini-2.5-flash` | Cheap + capable; cost is a dealbreaker. Set via `AGENT_LLM_MODEL=gemini-2.5-flash`. |

**Fallback behaviour:** the single Gemini call is wrapped with a timeout and try/except. On API error/rate-limit/timeout the `answer` node sets `state["error"]`, routing to `handle_error`, which records a `failed` run and returns human copy. No offline stub path — tests call the real Gemini API with keys from `.env`.

**Prompt strategy:** system/user split. The **system prompt** (`src/prompts/answer.md`) instructs the model to answer ONLY from the supplied profile, to give plain-English answers, and to state plainly when the profile is insufficient rather than fabricate row-level detail. The **user prompt** is a compact JSON serialization of `{question, profile}`. No few-shot needed; output is free-text plain English.

---

## Tools & Tool Calling

The agent calls **local pandas functions deterministically** (not LLM-selected tools). These are not exposed to the LLM as callable tools in Phase 1.

| "Tool" (local fn) | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `load_profile(dataset_id)` | Read local CSV, build the derived `DataProfile` | dataset_id | `DataProfile` (small dict) | Reads local disk only; no network |
| `LLMClient.call_model` | One Gemini call with question + profile | prompt, system | answer text | Network → Gemini |

**Tool selection strategy:** none — deterministic pipeline, no LLM tool choice in Phase 1.
**Tool failure handling:** `load_profile` failure → fatal (error). Gemini failure → fatal (error). Both route to `handle_error`.

---

## Agent State

Extends the skeleton's `AgentState` (`src/graph/state.py`). `messages` from the skeleton is unused in Phase 1 (no conversation memory) and kept for compatibility.

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                  # set by the runner at init

    # Input
    dataset_id: str              # set by the runner from the request
    question: str                # set by the runner from the request

    # Pipeline data (populated progressively by nodes)
    profile: dict                # set by load_profile (LOCAL pandas) — schema+stats+examples
    prompt: str                  # set by build_prompt — the EXACT user-prompt string sent to LLM
                                 #   (question + profile only; asserted to contain no raw rows)

    # Output
    answer: str                  # set by answer node from the Gemini response
    status: str                  # set by finalize/handle_error: "completed" | "failed"

    # Control
    error: str | None            # set by any node on fatal failure
    messages: list               # unused in Phase 1 (kept from skeleton for compatibility)
```

---

## Nodes / Steps

### `load_profile`

**Reads from state:** `dataset_id`
**Writes to state:** `profile`, `error`
**LLM call:** no.
**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Read `data/datasets/{dataset_id}.csv`, `pd.read_csv`, derive `DataProfile` | fatal (set `error` = "Dataset not found or unreadable") |

**Behaviour:** loads the raw CSV **locally** and computes the compact `DataProfile` (schema, row_count, per-column dtype + summary stats + ≤5 truncated example values). The raw DataFrame stays in this node's local scope and is **never** put into state fields that flow to the LLM — only the derived `profile` dict is written. This is the local side of the data boundary.

### `build_prompt`

**Reads from state:** `question`, `profile`
**Writes to state:** `prompt`, `error`
**LLM call:** no.
**External calls:** none.
**Behaviour:** serializes **only** `{question, profile}` into a compact JSON user-prompt string and stores it in `state["prompt"]`. This is the **boundary-enforcement node**: it provably constructs the LLM input from the profile alone. A test asserts the raw CSV/full-row content is absent from `state["prompt"]`. On a serialization error → `error`.

### `answer`

**Reads from state:** `prompt`
**Writes to state:** `answer`, `error`
**LLM call:** yes — `LLMClient().call_model(state["prompt"], system=<answer.md>)`, model `gemini-2.5-flash`, output plain text.
**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini | One generate-content call with question + profile only | fatal (set `error`), wrapped with timeout + try/except |

**Behaviour:** the only network/LLM step. Sends the boundary-safe prompt to Gemini and stores the plain-English answer. Logs token-frugal context (model, prompt length, latency) via observability — never logs raw rows.

### `finalize`

**Reads from state:** `answer`
**Writes to state:** `status = "completed"`
**Behaviour:** marks success; the runner persists `answer` + `status` to `RunRow`.

### `handle_error`

**Reads from state:** `error`, `run_id`
**Writes to state:** `status = "failed"`
**Behaviour:** terminal error sink; the runner persists `status=failed` + the human-readable `error` to `RunRow`. Logs the error with `run_id`.

---

## Graph / Flow Topology

```
START
  │
  ▼
load_profile ──(error)──► handle_error ──► END
  │
  ▼
build_prompt ──(error)──► handle_error ──► END
  │
  ▼
answer ───────(error)──► handle_error ──► END
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `load_profile` | `state.get("error")` | `handle_error`, else `build_prompt` |
| `build_prompt` | `state.get("error")` | `handle_error`, else `answer` |
| `answer` | `state.get("error")` | `handle_error`, else `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | profile, prompt, answer |
| **Across runs** | SQLite (`DatasetRow`, `RunRow`) | dataset metadata + schema; question/answer history |
| **Conversation** | none in Phase 1 | Each ask is independent. Conversation memory (follow-up questions referencing prior turns) is **deferred** — see [roadmap.md](roadmap.md#out-of-scope--deferred). |

> **Assumed:** conversation memory is deferred past Phase 1. The intake describes a question→answer tool (upload a file, ask a question, get an answer), not a chat thread; the primary value is grounded single-shot answers. The skeleton's `messages` field is retained so adding turn memory later is a small change. If the user wants follow-up/chat memory, it becomes a fast-follow phase.

**Context window management:** the prompt is intrinsically small (profile + question), so no summarization/RAG is needed. Profile example values and group counts are capped to keep tokens (and cost) low.

---

## Human-in-the-Loop Checkpoints

None within a run. The human testing gate is at phase boundaries (build-time), not inside the agent.

---

## Error Handling & Recovery

**Node-level:** each node wraps its work in try/except; on a fatal failure it sets `state["error"]` and the conditional edge routes to `handle_error`.

**Graph-level (`handle_error`):**
- Reads: `state.error`, `state.run_id`
- Runner updates `RunRow`: status → `failed`, `error_message`, `updated_at`
- Logs error with `run_id`
- Terminates the graph

**Resume / retry strategy:** no checkpointing in Phase 1; a failed ask is simply re-submitted by the user (idempotent — re-profiles the local file).
**Partial failure:** there are no non-critical steps in Phase 1 — every node is on the single answer path, so any failure aborts cleanly with human copy.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One log context per run keyed by `run_id` | structlog (`src/observability/events.py`), stdout JSON |
| **LLM calls** | model, prompt length (chars), latency, completion length — NEVER raw rows | structured log |
| **Local ops** | `load_profile` (dataset_id, row_count, n_columns), `build_prompt` (prompt length) | structured log |
| **Run outcome** | status, error if any | DB (`RunRow`) + structured log |

Phase 1 logs only its real operations (load_profile, the Gemini call, run outcome) — proportional, not gold-plated.

---

## Concurrency Model

- **Run isolation:** one ask at a time per request, scoped by `run_id`. The personal single-user tool needs no queue; concurrent requests are independent (each its own `RunRow`).
- **Parallel nodes within a run:** none — the pipeline is linear.
- **Checkpointing:** none (no human-in-the-loop, short-lived runs).

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("load_profile", load_profile)
graph.add_node("build_prompt", build_prompt)
graph.add_node("answer", answer)
graph.add_node("finalize", finalize)
graph.add_node("handle_error", handle_error)

graph.set_entry_point("load_profile")

graph.add_conditional_edges(
    "load_profile",
    lambda s: "handle_error" if s.get("error") else "build_prompt",
    {"handle_error": "handle_error", "build_prompt": "build_prompt"},
)
graph.add_conditional_edges(
    "build_prompt",
    lambda s: "handle_error" if s.get("error") else "answer",
    {"handle_error": "handle_error", "answer": "answer"},
)
graph.add_conditional_edges(
    "answer",
    lambda s: "handle_error" if s.get("error") else "finalize",
    {"handle_error": "handle_error", "finalize": "finalize"},
)

graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
