# Agentic Architecture — The Stack

This is the reference architecture every agent built from this boilerplate targets. It defines the
**agentic AI stack** as ten layers, names the canonical pattern doc and default technology for each, and
states what ships in the default baseline vs. what's added when it earns its place.

The orchestration framework is **LangGraph** (the `graph/StateGraph` layout in `project-layout.md`) and
the tool/integration standard is **MCP** (Model Context Protocol) — used **everywhere**, for internal
tools as well as external integrations, so every capability speaks one protocol. The Claude Agent SDK is
a viable alternative for Claude-native, lighter agents — note it in `02-architecture.md` if chosen, but
the default layout and patterns below assume LangGraph + MCP.

Everything is **real from Phase 1** — real LLM, real MCP tools, real DB. There are no stubs, no offline
mode (→ [`patterns/llm-providers.md`](patterns/llm-providers.md)).

---

## The stack (bottom-up)

| # | Layer | Canonical home | Default technology |
|---|-------|----------------|--------------------|
| 1 | **Model** | [`patterns/llm-providers.md`](patterns/llm-providers.md) | provider chosen at intake (Anthropic recommended), built via `init_chat_model`; structured outputs, prompt caching, extended thinking; routing earns its place |
| 2 | **Context** | [`patterns/memory-and-context.md`](patterns/memory-and-context.md) | system-prompt assembly, window management, compaction/summarization |
| 3 | **Memory** | [`patterns/memory-and-context.md`](patterns/memory-and-context.md) | working (graph state) · short-term (session) · long-term episodic+semantic (vector store) |
| 4 | **Tools / integration** | [`patterns/tools-and-mcp.md`](patterns/tools-and-mcp.md) | typed tool registry + **MCP everywhere** (internal + external) + action-safety sandbox |
| 5 | **Retrieval / knowledge** | [`patterns/retrieval.md`](patterns/retrieval.md) | embeddings + vector DB + chunking + hybrid search + rerank (RAG) — *earns its place* |
| 6 | **Orchestration** | [`patterns/react-agent.md`](patterns/react-agent.md) (single) · [`patterns/multi-agent.md`](patterns/multi-agent.md) (topologies) | ReAct loop default; supervisor / worker when it earns it |
| 7 | **Guardrails + HITL** | [`patterns/guardrails-and-hitl.md`](patterns/guardrails-and-hitl.md) | action-safety validation (baseline); input/output guardrails + HITL interrupt → resume earn their place |
| 8 | **Durability / runtime** | [`patterns/durability.md`](patterns/durability.md) | LangGraph checkpointer, resumable runs, concurrency — *earns its place* |
| 9 | **Observability + evals** | [`patterns/observability-and-evals.md`](patterns/observability-and-evals.md) | OTel GenAI traces + token/cost + eval skeleton (baseline); latency dashboards + LLM-judge suite earn their place |
| 10 | **Interface / serving** | [`../product/05-api.md`](../product/05-api.md) · [`../product/06-ui.md`](../product/06-ui.md) · [`project-layout.md`](project-layout.md) | async FastAPI + SSE streaming; Next.js + React + Tailwind UI; HTTP API + UI default trigger |

Exact library versions and providers for each layer are in [`tech-stack.md`](tech-stack.md) §
Agentic Stack Tech — that table is the single source of truth; this one names the *concepts*.

---

## Reference architecture

Baseline path in solid arrows; earns-its-place layers marked `*`.

```
trigger (HTTP API + UI default)
  → API (async FastAPI, SSE stream)
  → guardrails: action-safety validation                      (layer 7)
  → orchestrator: LangGraph StateGraph                         (layer 6)
       ├─ context assembly  ← memory (working/short)           (layers 2, 3)
       │                    ← long-term memory* / retrieval*    (layers 3, 5)
       ├─ plan_action (LLM via init_chat_model)                (layers 1, 6)
       ├─ act: tools / MCP  ← action-safety sandbox            (layer 4)
       ├─ observe → loop   (ReAct; supervisor/worker*)         (layer 6)
       ├─ guardrails: HITL approval (interrupt → resume)*      (layers 7, 8)
       └─ finalize / force_finalize (via finish tool)
  → persistence (runs, messages; checkpoints*)                 (layers 3, 8)
  → observability (OTel traces, token/cost, evals)             (layer 9)
```

This is the same ReAct skeleton from [`patterns/react-agent.md`](patterns/react-agent.md), with the
memory, tool, action-safety, and observability layers wired around it at baseline — and retrieval,
HITL, and durability added when they earn their place.

---

## The default baseline (what every agent ships)

Per the "raise the baseline" decision, the standard build is **not** a bare loop — and it is **real, not
stubbed**. Phase 1 delivers a complete working agentic baseline with these layers live:

- **Model** — real LLM via `init_chat_model`, provider chosen at intake, key required everywhere.
- **Working + short-term memory** — graph state + session-scoped store.
- **Tools via MCP** — at least one real MCP tool, behind the action-safety boundary.
- **Action-safety guardrail** — typed-arg validation + the safe-executor boundary.
- **Eval harness skeleton** — a tiny fixed dataset + ≥1 loose assertion, running in CI against the real model.
- **Observability baseline** — structured per-`run_id` logs + token/cost on the run + **OTel GenAI traces**.

See [`phases.md`](phases.md) for exactly which layer lands in which phase and its gate.

## Earns-its-place (added when the spec calls for it)

These are real layers, not gold-plating — but they're added in a later phase, only when the agent's job
needs them. The spec (`02-architecture.md` § Agentic stack layers used) records which apply and why:

- **Retrieval / RAG** — when answers depend on a knowledge corpus.
- **Long-term memory** (episodic/semantic) — when the agent must remember across sessions.
- **Model routing** (multiple models by task) — when one model isn't the right cost/quality fit.
- **Input + output guardrails** — when the agent ingests untrusted content or returns high-stakes answers.
- **Multi-agent (supervisor / worker)** — when a single ReAct loop can't keep the task coherent
  ([`patterns/multi-agent.md`](patterns/multi-agent.md) § Escalation criteria).
- **Human-in-the-loop** — when an action is irreversible or high-stakes.
- **Durable execution / checkpointing** — when runs are long, resumable, or must survive a restart.
- **Advanced observability** — aggregate metrics/latency dashboards + a richer eval suite beyond the Phase 1 baseline.

---

## How to use this file

1. `02-architecture.md` declares **which layers** this agent uses (all baseline layers + any
   earns-its-place ones) and why.
2. `tech-stack.md` § Agentic Stack Tech pins the **exact technology** per layer.
3. `07-agent-graph.md` specs the **graph** that wires the chosen layers together.
4. Each layer's behaviour is defined once in its pattern doc — never restate it elsewhere; link.
