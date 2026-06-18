# Pattern: Durability & Runtime

**Canonical home for layer 8 (Durability / runtime)**
([`../agentic-architecture.md`](../agentic-architecture.md)). How runs survive interruptions, resume,
and run concurrently without corrupting each other.

---

## Checkpointing

A LangGraph **checkpointer** persists graph state after each node, keyed by a `thread_id`. This is what
makes a run **resumable** — if the process dies, a node times out, or the run pauses for human approval,
it resumes from the last checkpoint instead of restarting.

- **Default:** `PostgresSaver` (matches the Postgres default stack); `SqliteSaver` for demos. Pick from
  [`../tech-stack.md`](../tech-stack.md) § Agentic Stack Tech.
- **`thread_id` = the session/conversation**, so follow-up turns share durable state. Don't confuse it
  with `run_id` (one invocation) — see the run-vs-session lifecycle in [`react-agent.md`](react-agent.md).
- Checkpointing is also the mechanism behind **HITL** interrupt → resume
  ([`guardrails-and-hitl.md`](guardrails-and-hitl.md)).

## Resumability & interrupts

- **Pause/resume** — `interrupt()` checkpoints and yields control; the API resumes by `thread_id` with
  the human's input.
- **Crash recovery** — on restart, a run resumes from its last checkpoint. Session-scoped in-memory
  resources (DataFrames, indexes) are gone after a restart — the API must return a clear, actionable
  error ("please re-upload"), per [`react-agent.md`](react-agent.md) § Resource lifecycle, not a 500.
- **Time/iteration bounds** — the max-iterations guard and `force_finalize` still apply
  ([`react-agent.md`](react-agent.md)); long runs check a wall-clock budget too.

## Concurrency

- **One run per thread at a time** — enforce at the API layer (return `409` if a run is already active
  on that `thread_id`). Concurrent writes to one thread's state corrupt it.
- **Different threads run in parallel** freely — they have isolated state and checkpoints.
- **Background execution** — long runs execute in a worker/background task, not inline in the request;
  the API returns a `run_id` and the client polls or streams (SSE) progress from `action_history`.

Idempotency for side-effecting actions (a key derived from `run_id` + action so a resume-after-crash
doesn't double-fire) is **not prescribed by the boilerplate** — add it per-action when a real
side-effecting integration needs the guarantee, and spec it there.

## Phasing

Baseline — short async runs; persistence is the `runs`/`messages` tables, no checkpointer. The
checkpointer + resumable/background execution earn their place when runs become long, interruptible, or
must survive a restart; idempotency keys, if needed at all, land with the first real side-effecting
action. Authority: [`../phases.md`](../phases.md) § Agentic layers by phase.
