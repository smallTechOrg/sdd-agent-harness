# Agent

> The code-execution agent graph for the Personal Data Analysis Agent. Built on the skeleton's compiled LangGraph `agentic_ai`, replacing the `transform_text` slot in place. Maps to `src/graph/{state,nodes,edges,agent,runner}.py`.

---

## Agent Architecture Pattern

**Chosen:** **Graph (LangGraph)** implementing **LLM-Generated Code Execution** (`agentic-ai.md` #22) as the core, wrapped in a **ReAct-style reason→act→observe loop** (#17/#5) — `generate_code` (reason/act) → `execute_locally` (observe) → revise — with **Exception Handling & Recovery** (#12, the revise-on-error loop with a cap), **Resource-Aware Optimization** (#16, cheap-tier model + cost accounting), **Guardrails** (#18, static import denylist + privacy redaction), and **Memory Management** (#8, conversation history threaded into the plan node — Phase 2). A graph (not a bare loop) because there are conditional edges: simple vs multi-step routing, the revise loop with a max-iteration cap, and an error path.

> Reflection (#4), multi-agent (#7), and planning beyond a single plan node are deliberately NOT used — they add latency/cost the smallest win does not need.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan` | Gemini | `gemini-2.5-flash` (env `AGENT_LLM_MODEL`) | Cheap routing/outline; low latency |
| `generate_code` | Gemini | `gemini-2.5-flash` | Flash handles pandas/SQL codegen well; keeps cost low |
| `summarize` | Gemini | `gemini-2.5-flash` | Prose over a small result — cheap tier ample |
| `select_chart` | Gemini | `gemini-2.5-flash` | Small structured pick; could be rule-based fallback |

> Model id is read from settings (`AGENT_LLM_MODEL`), never hardcoded. Escalating any node to a stronger model is an env override.

**Fallback behaviour:** Each LLM call retries on transient Gemini errors (429/5xx) with exponential backoff (3 attempts). On persistent failure the node sets `state["error"]`, the run is marked `failed`, and the user sees the error and (if any code ran) what was tried. Tests call the real Gemini API via `.env` — there is no offline stub path.

**Prompt strategy:** System/user split per node, prompts in `src/prompts/*.md`. `generate_code` uses structured output: the model must return a single fenced code block assigning `result` (and optional `key_numbers`); a parser extracts the code. `select_chart` returns JSON (chart type + encodings) validated against a schema, with a rule-based fallback if invalid.

---

## Tools & Tool Calling

The "tool" in this code-execution agent is **local code execution** — the agent acts by writing code that the system runs, rather than calling a fixed API.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_code` (`src/analysis/engine.py::execute`) | Runs generated pandas/SQL on the FULL dataset locally | generated code string, dataset_id | `{result, key_numbers, stdout, error}` (result capped to privacy limits) | reads DuckDB/parquet; no external calls; no LLM exposure of bulk data |
| `make_llm_context` (`engine.py`) | Builds the ONLY dataset context the LLM may see | dataset_id, optional prior result | `{schema, sample (≤20 rows), result (capped)}` | none — the redaction point |

**Tool selection strategy:** Forced/deterministic — the graph always executes generated code locally; the LLM does not choose tools, it writes code that `execute_locally` runs.

**Tool failure handling:** `execute_code` exceptions are captured (not raised) and fed back to `generate_code` via the revise edge, up to `MAX_REVISIONS`. After the cap, the run finalizes with a flagged best-guess (last successful partial, or the error + attempted code).

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                       # set by runner
    dataset_id: str                   # set by runner (the dataset being analysed)
    session_id: str | None            # Phase 2: persistent session

    # Input
    question: str                     # user's plain-language question
    messages: list                    # conversation history (Phase 2); [] in Phase 1

    # LLM-facing context (privacy-bounded — the ONLY dataset data the LLM sees)
    llm_context: dict                 # {schema, sample, prior_result} from make_llm_context()

    # Pipeline data (populated progressively)
    plan: str                         # plan node output (approach + simple/multi flag)
    is_simple: bool                   # plan node: fast single-pass vs multi-step
    code: str                         # generate_code node: the pandas/SQL snippet
    exec_result: dict                 # execute_locally: {result, key_numbers, stdout, error}
    revisions: int                    # count of generate→execute retries (cap MAX_REVISIONS)

    # Output
    answer: str                       # summarize node: plain-language prose
    key_numbers: dict                 # headline numbers
    summary_table: dict               # the small result as {columns, rows}
    chart_spec: dict                  # select_chart: Plotly figure spec
    followups: list                   # Phase 2: suggested follow-up questions
    llm_payload: dict                 # exact context sent to the LLM (transparency)
    tokens_in: int                    # accumulated across nodes
    tokens_out: int
    cost_estimate: float

    # Control
    stage: str                        # "planning"|"coding"|"running"|"charting"|"done"
    error: str | None                 # set by any node on fatal failure
    flagged: bool                     # best-guess returned after exhausting revisions
```

> Phase 1 fields: everything except `session_id`, `messages` (empty), `followups` (empty). Those activate in Phase 2.

---

## Nodes / Steps

### `profile`
**Reads:** `dataset_id`. **Writes:** `llm_context`, `stage`.
**LLM call:** No. Calls `make_llm_context(dataset_id)` to assemble schema + sample (and Phase-2 full profile). This is where the privacy boundary is materialized.
**External calls:** DuckDB read (fatal → set error). **Behaviour:** Loads the bounded context the rest of the graph hands to the LLM. Never loads bulk rows into state.

### `plan`
**Reads:** `question`, `llm_context`, `messages`. **Writes:** `plan`, `is_simple`, `stage`, token counts.
**LLM call:** Yes (`prompts/plan.md`) → short approach + a `simple`/`multi` flag.
**Behaviour:** Decides fast single-pass vs multi-step and outlines the approach. Threads conversation history (Phase 2) so follow-ups resolve.

### `generate_code`
**Reads:** `question`, `plan`, `llm_context`, `exec_result` (on revise), `revisions`. **Writes:** `code`, `llm_payload`, `stage`, token counts.
**LLM call:** Yes (`prompts/generate_code.md`) → one fenced code block assigning `result` (+ optional `key_numbers`). On revise, includes the prior code + traceback.
**Behaviour:** Produces self-contained pandas/DuckDB-SQL that reads the full dataset and yields a small result. Records the exact assembled payload into `llm_payload`.

### `execute_locally`
**Reads:** `code`, `dataset_id`. **Writes:** `exec_result`, `stage`.
**LLM call:** No. Calls `engine.execute(code, dataset_id)` — static import denylist check, timeout, stdout capture, result truncation to privacy caps.
**External calls:** DuckDB/pandas (errors captured into `exec_result.error`, not raised). **Behaviour:** The observe step — runs the code on the FULL data locally and captures the small result or the error.

### `summarize`
**Reads:** `question`, `exec_result.result`, `key_numbers`, `flagged`. **Writes:** `answer`, `key_numbers`, `summary_table`, `stage`, token counts.
**LLM call:** Yes (`prompts/summarize.md`) → prose + key numbers over the SMALL result only. (Phase 3: streams.)
**Behaviour:** Turns the bounded result into a plain-language answer. If `flagged`, frames it as a best-guess and notes what was tried.

### `select_chart`
**Reads:** `exec_result.result`, `summary_table`. **Writes:** `chart_spec`, `stage`.
**LLM call:** Yes (`prompts/select_chart.md`) → JSON chart spec; rule-based fallback on invalid JSON (e.g. 2-col numeric → bar/line by dtype).
**Behaviour:** Auto-selects an interactive Plotly chart spec from the result shape.

### `suggest_followups` *(Phase 2 — stubbed in Phase 1: returns [])*
**Reads:** `question`, `answer`, `llm_context`. **Writes:** `followups`.
**LLM call:** Yes (Phase 2). **Behaviour:** Proposes 2–3 next questions.

### `handle_error`
**Reads:** `error`, `run_id`. **Writes:** `stage="done"`. **Behaviour:** Terminal error node; runner marks the run `failed` and surfaces the message.

**Phase 1 real vs stub:** `profile`, `plan`, `generate_code`, `execute_locally`, `summarize`, `select_chart`, `handle_error` are **REAL** in Phase 1 (revise loop capped at 1 retry in Phase 1, raised to `MAX_REVISIONS`=2 thereafter). `suggest_followups` is a **stub** (returns `[]`) until Phase 2.

---

## Graph / Flow Topology

```
START
  │
  ▼
profile ──(error)──► handle_error ──► END
  │
  ▼
plan ──(error)──► handle_error
  │
  ▼
generate_code ──(error)──► handle_error
  │
  ▼
execute_locally
  │
  ├─(exec error AND revisions < MAX)──► generate_code   (revise loop, revisions += 1)
  │
  ├─(exec error AND revisions >= MAX)─► summarize  (flagged = True, best-guess)
  │
  └─(ok)────────────────────────────► summarize
                                         │
                                         ▼
                                    select_chart
                                         │
                                         ▼
                                   suggest_followups   (stub→[] in Phase 1)
                                         │
                                         ▼
                                       finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `profile` | `state["error"]` | `handle_error` |
| `plan` | `state["error"]` | `handle_error` |
| `generate_code` | `state["error"]` | `handle_error` |
| `execute_locally` | `exec_result.error` and `revisions < MAX_REVISIONS` | `generate_code` (revise) |
| `execute_locally` | `exec_result.error` and `revisions >= MAX_REVISIONS` | `summarize` (set `flagged=True`) |
| `execute_locally` | no error | `summarize` |

> `is_simple` (fast single-pass) is realized by `plan` producing a one-shot code intent so `generate_code`→`execute_locally` resolve in a single pass with no revise — the loop still exists but is not entered. No separate branch node needed in Phase 1.

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | All pipeline fields above |
| **Across runs** | SQLite (`runs`, `datasets`) | Question, code, result, chart, tokens, cost, timestamps |
| **Conversation** | SQLite (`conversation`) + `messages` in state (Phase 2) | Prior turns threaded into `plan` so follow-ups resolve |

**Context window management:** Bounded by construction — the LLM only ever sees schema + ≤20 sample rows + a capped result, never bulk data, so the prompt stays small regardless of dataset size. Conversation history (Phase 2) is windowed to the last N turns.

---

## Human-in-the-Loop Checkpoints

None in Phase 1 (the agent returns a flagged best-guess rather than pausing). Phase 2+ adds an optional clarifying-question path when the plan node is low-confidence; until then, ambiguity resolves to a flagged best-guess. *(No checkpoint table — not applicable to the Phase-1 graph.)*

---

## Error Handling & Recovery

**Node-level:** Each LLM node catches its own exceptions → sets `state["error"]`. `execute_locally` captures execution errors into `exec_result.error` (NOT fatal — feeds the revise loop).

**Graph-level (`handle_error`):**
- Reads `state.error`, `state.run_id`
- Runner updates the `runs` row: status → `failed`, `error_message`, `completed_at`
- Logs the error with `run_id` context
- Terminates the graph

**Resume / retry strategy:** No checkpoint resume in Phase 1 (runs are short). The revise loop is the in-run recovery: regenerate code on execution error up to `MAX_REVISIONS`.

**Partial failure:** If execution keeps failing past the cap, the graph continues to `summarize` with `flagged=True` and returns a best-guess that shows the attempted code + last error — it degrades, never crashes.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One structured log line per run (run_id, dataset_id, stage timings, status) | structlog → stdout (`src/observability/events.py`) |
| **LLM calls** | prompt/completion tokens, model, per-node | structlog + accumulated to `runs` row |
| **Tool calls** | `execute_code`: code hash, success/error, latency, result size | structlog |
| **Run outcome** | status, total duration, cost, error | SQLite `runs` + structured log |

> LangSmith is optional (env `LANGCHAIN_TRACING_V2`); structured logging is the always-on baseline wired from Phase 1.

---

## Concurrency Model

- **Run isolation:** one analysis run at a time per process is the expected single-user load; runs are scoped by `run_id` and each gets its own DuckDB cursor. No 409 gating needed for a single local user, but state is `run_id`-scoped so concurrent runs do not collide.
- **Parallel nodes within a run:** none — the pipeline is sequential (each node depends on the prior).
- **Checkpointing:** none in Phase 1 (short runs, no human-in-the-loop). Not added unless a future phase needs resumable long runs.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph import nodes, edges

def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("profile", nodes.profile)
    g.add_node("plan", nodes.plan)
    g.add_node("generate_code", nodes.generate_code)
    g.add_node("execute_locally", nodes.execute_locally)
    g.add_node("summarize", nodes.summarize)
    g.add_node("select_chart", nodes.select_chart)
    g.add_node("suggest_followups", nodes.suggest_followups)  # stub→[] in Phase 1
    g.add_node("finalize", nodes.finalize)
    g.add_node("handle_error", nodes.handle_error)

    g.set_entry_point("profile")
    g.add_conditional_edges("profile", edges.guard_error, {"ok": "plan", "handle_error": "handle_error"})
    g.add_conditional_edges("plan", edges.guard_error, {"ok": "generate_code", "handle_error": "handle_error"})
    g.add_conditional_edges("generate_code", edges.guard_error, {"ok": "execute_locally", "handle_error": "handle_error"})
    g.add_conditional_edges("execute_locally", edges.after_execute,
                            {"revise": "generate_code", "summarize": "summarize"})
    g.add_edge("summarize", "select_chart")
    g.add_edge("select_chart", "suggest_followups")
    g.add_edge("suggest_followups", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()   # keep the skeleton's exported name
```
