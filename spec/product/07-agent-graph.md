# Agent Graph

> **Boilerplate status:** Required when the project uses an agent framework (LangGraph, CrewAI, AutoGen, etc.). Filled in by the tech-designer sub-agent as part of the tech design stage.
>
> If your project has no agent framework (e.g., it's a simple script or API), delete this file.
>
> The spec-reviewer treats this file as a **CRITICAL BLOCKER** — the tech design will not be approved if this file is absent or incomplete when an agent framework is in use.
>
> **If the agent acts on the outside world** (tools, data, search — see Rule #9), it must use a **ReAct loop**. This file must then answer the eight pre-coding questions in `spec/engineering/ai-agents.md` Section 10 — including the **action-safety boundary** (what the executor permits / how actions are validated / the sandbox) and what **`force_finalize`** synthesises when iterations run out. The State below must carry the loop-control and usage fields; Edge Topology must show the `plan_action → execute_action` loop with iteration exhaustion routed to `force_finalize` (best-effort), not a one-shot pipeline; and the `action_history` trace must be surfaced to the user live, not just logged.

---

## State

<!-- FILL IN: Define the agent's state type. Every field must be named and typed. -->

```python
class AgentState(TypedDict):
    # Identity
    run_id: int
    # ... add all fields

    # Pipeline data (populated progressively by nodes)
    # ...

    # Control
    error: str | None   # set by any node on fatal failure

    # ReAct loop only (omit for one-shot pipelines)
    action_history: list[dict]  # [{"action": str, "result": str, "is_error": bool}]
    iteration_count: int        # guarded against max_iterations → force_finalize
    llm_response: str           # raw last LLM output — router checks it for FINAL ANSWER

    # Usage accounting (persist on the run record — see Rule #10 mechanics)
    tokens_input: int
    tokens_output: int
    estimated_cost_usd: float | None
```

---

## Nodes

<!-- FILL IN: One section per node. -->

### `node_[name]`

**Reads from state:** <!-- field names -->

**Writes to state:** <!-- field names -->

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| <!-- system --> | <!-- what it calls --> | <!-- fatal (set error) or partial (log and continue) --> |

**Behaviour:** <!-- one paragraph describing what this node does -->

---

## Edge Topology

<!-- FILL IN: ASCII diagram of node flow. Show conditional edges explicitly. -->

```
START
  │
  ▼
node_a ──(error)──► node_handle_error ──► END
  │
  ▼
node_b
  │
  ▼
node_finalize
  │
  ▼
END
```

---

## Error Handler Node (`node_handle_error`)

<!-- FILL IN: What happens when a fatal error occurs. -->

- Reads: `state.error`, `state.run_id`
- Updates DB: run status → "failed", error_message, completed_at
- Logs error with run_id context
- Terminates graph

---

## Finalize Node (`node_finalize`)

<!-- FILL IN: How a successful run is closed out. -->

- Reads: `state.run_id`, `state.completed_*`, `state.failed_*`
- Updates DB: run status → "completed", posts_completed count, completed_at
- Logs run summary

---

## Force-Finalize Node (`node_force_finalize`) — ReAct loops only

<!-- FILL IN (ReAct agents only): best-effort close-out when iterations run out. Delete for one-shot pipelines. -->

- Reached when `iteration_count` hits `max_agent_iterations` or the last N actions all errored (Rule #10) — **not** a fatal error.
- Asks the LLM to synthesise the best answer it can from `action_history`, noting what is missing; never emits a bare "I couldn't answer."
- Updates DB: run status → "completed" (records the early-exit reason); persists `action_history` + usage fields.
- Releases the run's module-level resources (same cleanup as `finalize`).

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

# Conditional edges after nodes that can produce fatal errors
graph.add_conditional_edges(
    "node_a",
    lambda s: "handle_error" if s.get("error") else "node_b",
)

# Unconditional edges
graph.add_edge("node_b", "finalize")
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

compiled_graph = graph.compile()
```

---

## Concurrency Model

<!-- FILL IN: How concurrent runs are handled. -->

- **One run at a time** (enforced at API layer — returns 409 if a run is already active)
- OR: **Parallel nodes** within a single run (describe which nodes run in parallel and why)
- **Checkpointing:** <!-- none / SqliteSaver / PostgresSaver — and when it's needed -->
