# Agent

The conversational-analysis agent. Replaces the baseline `transform_text` slot in
`src/graph/`. This is REQUIRED — the project uses LangGraph.

## Privacy invariant (restated — non-negotiable)

Every node that calls the LLM passes **only** schema, dtypes, basic stats, a ≤5-row sample,
the user's question/turns, generated code, errors, and a head-truncated aggregated result
preview. **No node ever passes a full DataFrame or bulk raw rows to the LLM.** Enforced in
`src/analysis/profile.py` (`MAX_SAMPLE_ROWS = 5`) and asserted by
`tests/phase1/test_privacy_invariant.py`. See [architecture.md → Privacy Data-Flow Boundary](architecture.md).

## Agent Architecture Pattern

**Chosen:** **Graph (LangGraph)** composing **Planning (#6)** + **LLM-Generated Code Execution
(#22)** + **Reflection / inspect-refine loop (#4, #12)** + **Memory Management (#8,
conversation history)** + **Resource-Aware Optimization (#16, cheap-default / escalate-on-hard,
Phase 4)** + **Human-in-the-Loop (#13, clarify branch, Phase 4)**, wrapped with Guardrails
(#18, the privacy/execution constraints) and Observability (#19, per-run/per-node logging).

Rationale: questions are open-ended over structured data, so we must generate and run code
(#22), not map to a fixed op-list. Hard questions need a plan and an iterate loop; simple ones
take the cheap path. A conditional graph expresses the retry/refine cap, the
cheap-vs-deep routing, and the clarify-vs-best-guess branch cleanly.

| Pattern | Use when | Phase |
|---------|----------|-------|
| Graph (LangGraph) | multi-step pipeline with conditional retry/route edges | 1 |

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| plan | Gemini | `gemini-2.5-flash` | Cheap planning; escalate to `gemini-2.5-pro` on hard (P4) |
| generate_code | Gemini | `gemini-2.5-flash` | Code gen for common cases; escalate on hard (P4) |
| inspect_result | Gemini | `gemini-2.5-flash` | Lightweight judgment on whether the result answers the Q |
| answer | Gemini | `gemini-2.5-flash` | Phrase the final plain-English answer |
| suggest_followups | Gemini | `gemini-2.5-flash` | Cheap; can be a single combined call with answer |

**Fallback behaviour:** on a Gemini API error, retry with exponential backoff (up to 2
retries); if still failing, set `state["error"]` and route to `handle_error`, which records the
run as failed and surfaces a clear message. This is production resilience — tests still call the
**real** Gemini API with the key from `.env`.

**Prompt strategy:** system/user split. Prompts live in `src/prompts/*.md`:
- `plan.md` — given the profile + question + history, produce a short numbered plan.
- `generate_code.md` — given profile + plan + (P4) column notes, write a pandas snippet that
  assigns to `result`; output fenced code only.
- `inspect.md` — given the question + code + result preview + any error, decide
  `done | refine | clarify` and (P4) a difficulty signal.
- `answer.md` — given question + result preview, write the plain-English answer + 2-3 follow-ups.
Structured output: code via a fenced block (parsed out); inspect via a small JSON verdict.

---

## Tools & Tool Calling

The agent's single "tool" is the local pandas executor — it does not use LLM function-calling;
nodes orchestrate the tool deterministically.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_pandas` | Run generated snippet against the full DataFrame(s) | code str, named frames | `ExecutionResult{result, stdout, error}` | none (read-only on in-memory frame) |
| `load_dataset` | Load a saved file from `uploads/` into a DataFrame | dataset_id | DataFrame + profile | reads disk |
| `profile_dataset` | Build schema+stats+≤5-row sample | DataFrame | profile dict | none |

**Tool selection strategy:** deterministic — the graph calls `execute_pandas` after
`generate_code`; no LLM tool-choice.

**Tool failure handling:** an execution error is captured (not raised) and fed to
`inspect_result`, which routes to `refine` (regenerate code with the error) up to the
iteration cap, then degrades to a best-effort answer or `handle_error`.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                          # set at initialisation (runs row id)
    conversation_id: str                 # set at initialisation

    # Input
    question: str                        # user's natural-language question
    dataset_id: str                      # active dataset (P1: explicit; P4: auto-pick)
    history: list                        # [{role, content}] prior turns (conversation memory)

    # Context (built server-side; privacy-safe — schema/stats/sample only)
    profile: dict                        # column names, dtypes, stats, <=5-row sample
    column_notes: list                   # (P4) user-authored notes/business rules

    # Pipeline data (populated progressively by nodes)
    plan: str                            # numbered plan from plan node
    code: str                            # generated pandas snippet
    execution: dict                      # ExecutionResult: {result_preview, stdout, error}
    iteration: int                       # refine-loop counter (starts 0)
    verdict: str                         # inspect output: "done" | "refine" | "clarify"
    difficulty: str                      # (P4) "easy" | "hard" → model escalation

    # Output
    answer: str                          # final plain-English answer
    suggestions: list                    # 2-3 follow-up questions
    chart_spec: dict                     # (P3) {type, series} server-computed
    clarifying_question: str             # (P4) set when verdict == "clarify"

    # Cost / observability
    tokens: dict                         # {prompt, completion} accumulated (P2 surfaces in UI)
    cost_usd: float                      # estimated (P2)

    # Control
    error: str | None                    # set by any node on fatal failure
    status: str                          # "completed" | "failed" | "needs_clarification"
```

> Phase 1 populates: run_id, conversation_id, question, dataset_id, history, profile, plan,
> code, execution, iteration, verdict, answer, suggestions, status, error. `chart_spec`,
> `column_notes`, `difficulty`, `clarifying_question`, `cost_usd` are present in the type but
> filled by later phases (minimal/no-op nodes in P1).

---

## Nodes / Steps

### `load_profile`
**Reads:** `dataset_id`. **Writes:** `profile`, `history`, `column_notes` (P4).
**LLM call:** no. Loads the saved file from `uploads/` and builds the privacy-safe profile;
loads prior conversation turns. Fatal on missing/corrupt file → `error`.

### `plan`
**Reads:** `question`, `profile`, `history`. **Writes:** `plan`, `difficulty` (P4).
**LLM call:** yes (`plan.md`, flash). Produces a short numbered plan. In P1 may be a single
brief plan; P4 produces deeper plans and a difficulty signal.

### `generate_code`
**Reads:** `question`, `plan`, `profile`, `column_notes` (P4), `execution.error` (on refine).
**Writes:** `code`. **LLM call:** yes (`generate_code.md`). Emits a pandas snippet assigning to
`result`. On a refine pass, includes the prior code + error so the model fixes it.

### `execute_code`
**Reads:** `code`, `dataset_id`. **Writes:** `execution`. **LLM call:** no.
Runs the snippet against the **full** DataFrame via `src/analysis/execute.py` in a restricted
namespace with a timeout; captures `result` (head-truncated preview), stdout, and any error.
Never sends raw rows anywhere.

### `inspect_result`
**Reads:** `question`, `code`, `execution`, `iteration`. **Writes:** `verdict`, `iteration`.
**LLM call:** yes (`inspect.md`, flash). Decides `done` / `refine` / `clarify` (P4).
Increments `iteration`.

### `refine`
**Reads:** `execution.error`, `code`, `plan`. **Writes:** routes back to `generate_code`.
**LLM call:** no (pass-through; the regeneration happens in `generate_code`). P1: simple
pass-through enabling one or two retry passes on execution error.

### `clarify` (Phase 4)
**Reads:** `question`, `profile`. **Writes:** `clarifying_question`, `status="needs_clarification"`.
**LLM call:** yes. Asks the user a question instead of guessing. Human-in-the-loop (#13).

### `answer`
**Reads:** `question`, `execution`, `plan`, `code`. **Writes:** `answer`, `suggestions`,
`chart_spec` (P3), `tokens`/`cost_usd` (P2). **LLM call:** yes (`answer.md`, flash). Phrases
the plain-English answer and proposes 2-3 follow-ups. On a best-guess path, flags uncertainty.

### `finalize`
**Reads:** all output fields. **Writes:** `status="completed"`. Persists the run.

### `handle_error`
**Reads:** `error`, `run_id`. **Writes:** `status="failed"`. Records the run as failed,
surfaces the message.

---

## Graph / Flow Topology

```
START
  │
  ▼
load_profile ──(error)──► handle_error ──► END
  │
  ▼
plan ──(error)──► handle_error
  │
  ▼
generate_code ──(error)──► handle_error
  │
  ▼
execute_code ──(fatal error)──► handle_error
  │
  ▼
inspect_result
  │  verdict == "done"            → answer
  │  verdict == "refine" & iter<MAX → generate_code   (retry/refine loop)
  │  verdict == "refine" & iter>=MAX → answer (best-effort, flagged)
  │  verdict == "clarify" (P4)    → clarify ──► finalize (status=needs_clarification) ──► END
  ▼
answer ──► finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| load_profile / plan / generate_code / execute_code | `state["error"]` set | handle_error |
| inspect_result | `verdict == "done"` | answer |
| inspect_result | `verdict == "refine"` and `iteration < MAX_ITERATIONS` | generate_code |
| inspect_result | `verdict == "refine"` and `iteration >= MAX_ITERATIONS` | answer (best-effort) |
| inspect_result | `verdict == "clarify"` (P4) | clarify |
| clarify (P4) | always | finalize |
| answer | always | finalize |

> `MAX_ITERATIONS` (default 3) caps the refine loop — a Goal-Setting/Monitoring stop condition
> (#11). P1 wires the loop with the cap; deep iteration tuning is P4.

> **Cheap-path vs deep-path (P4):** the difficulty router on `plan`/`inspect_result` selects
> `gemini-2.5-flash` (easy) vs `gemini-2.5-pro` (hard) and a tighter vs looser iteration cap —
> Resource-Aware Optimization (#16). P1 always uses flash.

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph state | profile, plan, code, execution, iteration |
| Across runs | SQLite (`runs`, `datasets`) | past questions/code/results, profiles |
| Conversation | `messages` table → `state.history` | prior user/assistant turns for follow-ups |

**Conversation memory is a Phase-1 capability** (see
[capabilities/conversation-memory.md](capabilities/conversation-memory.md)): the `messages`
table exists in P1 and `load_profile` loads prior turns into `history`, which `plan` and
`generate_code` use so "now break that down by region" resolves against the previous answer.

**Context window management:** only the compact profile (not data) plus a windowed/truncated
turn history is sent; result previews are head-truncated. For long histories, older turns are
truncated (sliding window) — sufficient for a single user's session.

---

## Human-in-the-Loop Checkpoints

| Checkpoint | Shown to user | Expected action | Default |
|------------|---------------|-----------------|---------|
| clarify (P4) | A clarifying question when the agent is uncertain | User answers (new turn) | If user re-asks, agent may give a flagged best guess |

P1 has no human checkpoint — the core path runs to an answer.

---

## Error Handling & Recovery

**Node-level:** each node wraps its work in try/except; fatal errors set `state["error"]` and
the conditional edge routes to `handle_error`. Execution errors are NOT fatal — they're
captured in `state["execution"]["error"]` and drive the refine loop.

**Graph-level (`handle_error`):** reads `error`, `run_id`; sets run status → `failed`,
`error_message`; logs with `run_id`; terminates.

**Resume / retry:** the refine loop retries code generation up to `MAX_ITERATIONS` within a
run. LLM API errors retry with backoff inside the node. No cross-run resume needed for a single
user.

**Partial failure:** if refine exhausts the cap, the agent answers best-effort with the last
usable result and flags the uncertainty rather than failing the run.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| Trace | One log line per node per run with `run_id` | stdout structured log |
| LLM calls | model, prompt/completion tokens, latency | structured log + (P2) persisted to `runs` |
| Tool calls | execute_pandas: success/error, duration | structured log |
| Run outcome | status, total duration, error | `runs` table + log |

---

## Concurrency Model

- **Run isolation:** one agent run at a time per process is acceptable (single user). The API
  starts a run, persists a `runs` row, and runs the graph; concurrent requests are serialized
  at the app level. Heavy pandas work runs off the event loop (threadpool) so the server stays
  responsive.
- **Parallel nodes within a run:** none — the pipeline is sequential with a refine loop.
- **Checkpointing:** none in P1 (runs are short). The clarify branch (P4) persists state to the
  `runs`/`messages` tables rather than using a LangGraph checkpointer.

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("load_profile", load_profile)
graph.add_node("plan", plan)
graph.add_node("generate_code", generate_code)
graph.add_node("execute_code", execute_code)
graph.add_node("inspect_result", inspect_result)
graph.add_node("answer", answer)
graph.add_node("finalize", finalize)
graph.add_node("handle_error", handle_error)
# graph.add_node("clarify", clarify)   # Phase 4

graph.set_entry_point("load_profile")

def err(s): return "handle_error" if s.get("error") else None

graph.add_conditional_edges("load_profile",
    lambda s: "handle_error" if s.get("error") else "plan")
graph.add_conditional_edges("plan",
    lambda s: "handle_error" if s.get("error") else "generate_code")
graph.add_conditional_edges("generate_code",
    lambda s: "handle_error" if s.get("error") else "execute_code")
graph.add_conditional_edges("execute_code",
    lambda s: "handle_error" if s.get("error") else "inspect_result")
graph.add_conditional_edges("inspect_result", route_after_inspect, {
    "answer": "answer",
    "generate_code": "generate_code",   # refine loop (guarded by MAX_ITERATIONS)
    # "clarify": "clarify",             # Phase 4
})

graph.add_edge("answer", "finalize")
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()   # keep the exported name `agentic_ai`
```

`route_after_inspect`: returns `"answer"` if `verdict=="done"`, `"answer"` if
`verdict=="refine" and iteration>=MAX_ITERATIONS`, `"generate_code"` if
`verdict=="refine" and iteration<MAX_ITERATIONS` (and in P4 `"clarify"` if
`verdict=="clarify"`).
