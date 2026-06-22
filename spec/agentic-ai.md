# Agentic AI Design

> **Boilerplate status:** Required when the project uses an agent framework (LangGraph, CrewAI, AutoGen, multi-agent orchestration, etc.). Filled in by the tech-architect sub-agent as part of the tech design stage.
>
> If your project has no agent framework (e.g., a simple script or single-LLM API call), delete this file.
>
> The tech-architect treats this file as a **CRITICAL BLOCKER** — the tech design will not be approved if this file is absent or incomplete when an agent framework is in use.

---

## Agent Architecture Pattern

<!-- FILL IN: Which pattern does this agent follow? Choose one and describe why. -->

| Pattern | Use when |
|---------|----------|
| **Single-agent loop** | One LLM drives a deterministic tool-call loop. No branches, no handoffs. |
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges, checkpointing, or parallel nodes. |
| **Multi-agent** | Specialised sub-agents with distinct roles; orchestrator routes between them. |
| **Supervisor** | One supervisor LLM dispatches to worker agents based on task type. |
| **Human-in-the-loop** | Execution pauses at defined checkpoints for user review or approval. |

**Chosen:** <!-- state pattern + one-sentence rationale -->

---

## LLM Provider & Model

<!-- FILL IN: Which model drives each agent/node? State provider, model ID, and why. -->

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| <!-- node --> | Anthropic | <!-- e.g. claude-sonnet-4-6 --> | <!-- latency vs. quality trade-off --> |

**Fallback behaviour:** <!-- What happens if the LLM API is unavailable or rate-limited? -->

**Prompt strategy:** <!-- System/user split, few-shot examples, structured output (tool_use / JSON mode)? -->

---

## Tools & Tool Calling

<!-- FILL IN: Every tool the agent can call. -->

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| <!-- name --> | <!-- what it does --> | <!-- params --> | <!-- return type --> | <!-- DB write, API call, file write, etc. --> |

**Tool selection strategy:** <!-- How does the agent decide which tool to call? (LLM choice, rule-based routing, forced single tool) -->

**Tool failure handling:** <!-- retry, fallback, abort — per tool or global policy? -->

---

## Agent State

<!-- FILL IN: The full state type. Every field must be named, typed, and annotated with what populates it. -->

```python
class AgentState(TypedDict):
    # Identity
    run_id: int                          # set at initialisation

    # Input
    # ...                                # fields populated from the trigger

    # Pipeline data (populated progressively by nodes)
    # ...

    # Output
    # ...                                # final result fields

    # Control
    error: str | None                    # set by any node on fatal failure
    checkpoint: str | None              # last completed node (for resume)
```

---

## Nodes / Steps

<!-- FILL IN: One section per node. For single-agent loops, describe each "step" or "tool call phase." -->

### `node_[name]`

**Reads from state:** <!-- field names -->

**Writes to state:** <!-- field names -->

**LLM call:** <!-- yes/no; if yes: prompt template summary, model used, output format -->

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| <!-- system --> | <!-- what it calls --> | <!-- fatal (set error) / partial (log + continue) / retry --> |

**Behaviour:** <!-- One paragraph. What decision or transformation does this node perform? -->

---

## Graph / Flow Topology

<!-- FILL IN: ASCII diagram of node flow. Show ALL conditional edges explicitly. -->

```
START
  │
  ▼
node_a ──(error)──► node_handle_error ──► END
  │
  ▼
node_b ──(condition)──► node_c
  │                         │
  │                         ▼
  └──────────────────► node_finalize
                             │
                             ▼
                            END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| <!-- node --> | <!-- e.g. state["error"] is not None --> | <!-- target node --> |

---

## Memory & Context

<!-- FILL IN: How does the agent remember things across turns, steps, or runs? -->

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | All in-progress data |
| **Across runs** | <!-- DB / vector store / none --> | <!-- e.g. past results, user prefs --> |
| **Conversation** | <!-- message history / summary / none --> | <!-- if chat-style --> |

**Context window management:** <!-- How is the prompt kept within limits? (summary, sliding window, RAG retrieval) -->

---

## Human-in-the-Loop Checkpoints

<!-- FILL IN: Where does execution pause for human input? Delete section if not applicable. -->

| Checkpoint | What is shown to the user | Expected user action | Timeout / default |
|------------|--------------------------|----------------------|-------------------|
| <!-- name --> | <!-- what the agent surfaces --> | <!-- approve / edit / abort --> | <!-- timeout action --> |

---

## Error Handling & Recovery

<!-- FILL IN: How the agent handles failures at each level. -->

**Node-level:** <!-- Each node catches its own exceptions; fatal errors set state["error"] and route to handle_error node. -->

**Graph-level (handle_error node):**
- Reads: `state.error`, `state.run_id`
- Updates DB: run status → "failed", `error_message`, `completed_at`
- Logs error with `run_id` context
- Terminates graph

**Resume / retry strategy:** <!-- Can a failed run be resumed from its last checkpoint? How? -->

**Partial failure:** <!-- If a non-critical step fails, does the agent degrade gracefully or abort? -->

---

## Observability

<!-- FILL IN: What is logged, traced, and measured? -->

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One trace per run, one span per node | <!-- OpenTelemetry / LangSmith / stdout --> |
| **LLM calls** | Prompt tokens, completion tokens, latency, model | <!-- LangSmith / structured log --> |
| **Tool calls** | Tool name, inputs, success/error, latency | Structured log |
| **Run outcome** | Status, total duration, error if any | DB + structured log |

---

## Concurrency Model

<!-- FILL IN: How concurrent agent runs are handled. -->

- **Run isolation:** <!-- one-at-a-time (API returns 409) / queue / parallel with run_id scoping -->
- **Parallel nodes within a run:** <!-- which nodes run in parallel and why -->
- **Checkpointing:** <!-- none / SqliteSaver / PostgresSaver — required if human-in-the-loop or long-running -->

---

## Graph Assembly (`agent/graph.py`)

<!-- FILL IN: Pseudocode showing how nodes and edges are wired. Must be ≤ 60 lines in the real file. -->

```python
graph = StateGraph(AgentState)

graph.add_node("node_a", node_a)
graph.add_node("node_b", node_b)
graph.add_node("finalize", node_finalize)
graph.add_node("handle_error", node_handle_error)

graph.set_entry_point("node_a")

graph.add_conditional_edges(
    "node_a",
    lambda s: "handle_error" if s.get("error") else "node_b",
)

graph.add_edge("node_b", "finalize")
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

compiled_graph = graph.compile()
```
