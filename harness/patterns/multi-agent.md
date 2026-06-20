# Pattern: Multi-agent (supervisor + sub-agents) — Layer 6

A second-tier capability. The default single ReAct loop (`patterns/react-agent.md`) handles almost
everything — reach for this **only when one loop cannot keep the task coherent** (criteria below).
**Generate fresh at build time**, pinning the *current* `langgraph` (verify latest first — a guessed
version 404s). The code below is the proven loop wired into a subgraph.

## When it earns its place (escalation criteria)
Add a supervisor only when at least one holds — otherwise a single loop wins on cost and latency:
- **Context blow-out** — the task needs more retrieved/scanned material than fits one window coherently
  (read 30 files, summarize each), so intermediate junk crowds out the goal.
- **Independent fan-out** — sub-tasks are parallelizable and don't depend on each other (research N angles,
  check N candidates); serial iteration in one loop is needlessly slow.
- **Distinct tool/skill sets** — sub-tasks want different, conflicting toolboxes you don't want all live in
  one prompt (a writer vs. a code-runner).

If none hold, stop — keep the single loop. One level of delegation only; a sub-agent does **not** spawn
its own sub-agents (depth > 1 is where coherence and cost both fall apart).

## The sub-agent pillar: isolated context, summary return
The whole point (the Deep-Agent sub-agent pillar): each sub-agent runs its **own** ReAct loop in a **fresh
message list** — it reads its slice, does the work, and returns a **~1–2k-token summary**, not its raw
transcript. The supervisor's context grows by summaries, not by every tool result the sub-agent saw. That
isolation is what buys coherence on long tasks; lose it (dump the full sub-transcript back) and you've
just built a slower single loop.

## Shape
```
supervisor → (spawn sub-agent → sub-agent runs its own loop → returns summary)* → supervisor → finalize
```
The supervisor is itself a ReAct loop (`patterns/react-agent.md`) whose tools include a `delegate` tool.
Each `delegate(task, agent)` call invokes a compiled sub-graph and lands only its summary in the
supervisor's messages.

## Code — `agent/multi_agent.py`
Reuses `build_graph` (the ReAct loop) for every sub-agent. The sub-agent graph is the same compiled graph
from `patterns/react-agent.md`; the supervisor just calls it as a tool and keeps the summary.
```python
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from .config import get_settings
from .graph import build_graph          # patterns/react-agent.md — the ReAct loop
from .llm import get_model              # patterns/model-and-providers.md — get_model(tier=...)
from .observability import span         # patterns/observability-and-evals.md
from .state import AgentState           # +run_id

# Each sub-agent gets its OWN compiled graph + a fresh message list (isolated context).
# Route sub-agents to the CHEAP tier; the supervisor runs on a stronger tier (cost note below).
SUB_PROMPTS = {
    "researcher": "You research one angle. Use your tools, then call finish with a 1-2k-token summary.",
    "file_ops":   "You read/transform files. Do the edits, then call finish with a short summary of what changed.",
}

async def run_sub_agent(kind: str, task: str, run_id: str) -> str:
    model = get_model(tier="cheap")                 # sub-agents are the bulk of the calls → cheap
    sub = build_graph(model)
    state: AgentState = {
        "messages": [SystemMessage(SUB_PROMPTS[kind]), HumanMessage(task)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }
    async with span(run_id, f"invoke_agent.sub.{kind}", "AGENT", task=task) as sp:
        result = await sub.ainvoke(state, config={"recursion_limit": 50})
        summary = result["answer"] or "(sub-agent produced no summary)"
        sp["summary_preview"] = summary[:300]
    return summary                                  # ONLY the summary returns to the supervisor

def make_delegate_tool(run_id: str):
    @tool
    async def delegate(agent: str, task: str) -> str:
        """Delegate a self-contained sub-task to a sub-agent (researcher|file_ops).
        The sub-agent runs in isolated context and returns a short summary."""
        if agent not in SUB_PROMPTS:
            return f"unknown agent '{agent}'. choose: {', '.join(SUB_PROMPTS)}"
        return await run_sub_agent(agent, task, run_id)
    return delegate
```

Wire the supervisor as a normal ReAct graph whose `TOOLS` include `make_delegate_tool(run_id)` alongside
`write_todos` + `finish` (`patterns/react-agent.md`, `patterns/tools-and-mcp.md`). The supervisor runs on a
**stronger tier** so its planning/decomposition is sound:
```python
supervisor = build_graph(get_model(tier="orchestrator"))   # stronger tier — it plans, it doesn't grind
```
`get_model(tier=...)` resolves to the per-role model IDs in `spec/tech-stack.md` (e.g. orchestrator →
Sonnet-4.6 class, cheap → Haiku-4.5 / Gemini-flash class) → `patterns/model-and-providers.md`.

## Mandatory mechanics (do not omit)
- **Isolated context** — fresh message list per sub-agent; never thread the supervisor's history in.
- **Summary-only return** — the sub-agent's `finish` answer is the contract; raw transcripts stay inside.
- **One level deep** — `SUB_PROMPTS` agents have no `delegate` tool; depth > 1 is a bug, not a feature.
- **Spans** — every sub-agent invocation is its own `invoke_agent.sub.<kind>` span, nested under the run →
  `patterns/observability-and-evals.md`. The `/traces` viewer renders the tree.

## Cost note (route by tier)
This is where multi-agent pays for itself or bankrupts you. Orchestration is a few high-value calls;
sub-agents and file-ops are the long tail.
- **Supervisor (orchestrator tier, stronger):** decomposition, routing, final synthesis. Few calls, high
  leverage — a wrong plan wastes every sub-agent below it.
- **Sub-agents / file-ops (cheap tier):** the bulk of the calls and tokens. A summary-return contract keeps
  each one's output small, so the cheap tier is enough.
Pin the exact IDs in `spec/tech-stack.md` (verify current before pinning — an old ID 404s). The runtime
default is the cheap tier; the orchestrator tier is the deliberate upgrade for the supervisor only.

## Gate (the test that proves it — run it, don't trust it)
Drive the supervisor with a `FakeModel` (no key, `patterns/react-agent.md`) scripted to call
`delegate` once then `finish`; stub `run_sub_agent` to return a fixed summary. Assert: the supervisor's
context contains the **summary** and not the sub-agent's tool results (isolation held), an
`invoke_agent.sub.*` span was recorded, and the run finalized. → `workflows/gates.md`.
