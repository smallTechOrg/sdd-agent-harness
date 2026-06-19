---
description: Add one capability to a built agent end to end — EARS file, tool/node, eval pair, gate, delta record.
argument-hint: "<capability>"
---

# Workflow: `/spec-new-capability`

Add one capability to a *built* agent, end to end: write its EARS file, make it real from the relevant
recipe, wire its eval, run the gate, record the delta. This is the steady-state loop after `/build` — it is
**spec-first** (the EARS file is the contract; code and eval follow it) and ends, like everything here, on a
**mechanical gate** — not prose. Read `harness/harness.md` first (the law); this file sequences the recipes,
it never restates them.

**Preconditions.** A working agent (`/build` already green) and a funded `APP_LLM_API_KEY` for the real run.
Work on a `feature/<slug>-<date>` branch into a PR — hooks handle secrets/branch rules (`harness.md`).

## One capability = one EARS file → one tool/node → one eval pair → one gate

### 1. Write the EARS file — `spec/capabilities/<slug>.md`
Spec before code. One capability per file; each acceptance line is an **EARS** statement
(`WHEN <trigger> the system SHALL <response>`) that feeds the eval gate verbatim. This is the
**spec-writer's** job (`agents/spec-writer.md`) — don't skip it; an untracked capability has no gate.

```markdown
# Capability: <name>

## What & why
<one paragraph: the user-visible behaviour and why it matters to the success criteria in spec/product.md>

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN <trigger> the system SHALL <observable response>.
- WHILE <state> WHEN <trigger> the system SHALL <response>.   # event/state variants

## Tools & layers touched
- tool: <name>  (in-process @tool | MCP — patterns/tools-and-mcp.md)
- layers: <e.g. retrieval ON — patterns/retrieval.md>         # only layers already/now ON in spec/agent.md

## Evaluation
- outcome evaluation_steps: <2–4 rubric bullets the LLM-judge scores 0–5 against>
- expect_tools: [<tool>]      forbid_tools: [<mutating tool that must NOT fire ungated>]
```
If the capability turns on a *new* layer (retrieval, memory, multi-agent, HITL…), flip it ON in
`spec/agent.md` first and follow that layer's recipe — a capability never silently enables a layer.

### 2. Generate the tool/node from the recipe — don't hand-roll
Pick the **cheapest tool layer that works** (`patterns/tools-and-mcp.md` § 3-layer model): own it →
in-process `@tool`; cross a process/trust boundary → MCP. Add the tool to `TOOLS`; the ReAct loop binds and
routes it unchanged (`patterns/react-agent.md`). A new in-process tool is just an entry in `agent/tools.py`:

```python
# agent/tools.py — append; it joins TOOLS / TOOL_MAP / bind_tools with zero loop changes.
from langchain_core.tools import tool

@tool
def <name>(<typed args>) -> str:
    """<one line the model reads as the description — typed signature derives the schema>."""
    ...
    return result            # return a string/JSON string; FAIL SOFT — return "error: ..." , never raise

TOOLS.append(<name>); TOOL_MAP[<name>.name] = <name>
```
- **Mutating / irreversible** tool (send, charge, delete, post) → gate it before merging
  (`patterns/guardrails-and-hitl.md`); never let force-finalize fire it unguarded (`tools-and-mcp.md`).
- **External** integration → MCP, OAuth 2.1, no static secrets, allowlisted server
  (`patterns/tools-and-mcp.md` § MCP security). The `execute_tool.<name>` span is its audit trail.
- A whole new **node/sub-agent** (not just a tool) → `patterns/react-agent.md` / `patterns/multi-agent.md`.

Every LLM and tool step is already span-wrapped by the loop (`patterns/observability-and-evals.md`) — the new
tool shows up at `/traces` for free; no extra instrumentation.

### 3. Add the eval — one EARS line ⇒ one outcome + one trajectory assertion
Reuse `outcome_eval` / `trajectory_eval` from `agent/evals.py` (`patterns/observability-and-evals.md`); map
the EARS line and the file's `## Evaluation` block straight in. Add **one** case to the gate suite:

```python
# tests/test_<slug>_gate.py
async def test_<slug>_gate():
    run_id = "gate-<slug>"
    state = await run_agent("<a goal that exercises the capability>", run_id=run_id)   # real run, real model
    ok_o, score, _ = await outcome_eval(
        goal="<same goal>", answer=state["answer"],
        criterion="WHEN <trigger> the system SHALL <response>.",          # the EARS line, verbatim
        evaluation_steps=[ ... ])                                         # the file's outcome bullets
    ok_t, reasons = await trajectory_eval(
        run_id, expect_tools=["<name>"], forbid_tools=["<mutating tool>"])
    assert ok_o, f"OUTCOME failed: score {score}"     # a 200 with a wrong answer FAILS here
    assert ok_t, f"TRAJECTORY failed: {reasons}"
```
The deterministic **trajectory** half also runs in CI with no key — drive `run_agent` with the FakeModel from
`patterns/react-agent.md`. The **outcome** (LLM-judge) half needs the funded key and runs in the demo gate.

### 4. Run the gate — this is "done", not your opinion
"Done" = the gate script exits 0 (`harness.md`, `workflows/gates.md`). Run it; don't trust it:

```bash
APP_LLM_API_KEY=… pytest tests/test_<slug>_gate.py -q   # real run + both evals → exit 0 or it isn't done
```
A passing `/health`, a wrong answer, a missing/duplicate tool call, or an ungated mutating tool all **fail**
the gate. Server boots, `/health` 200, the real run completes, the **outcome eval passes**, the new
`execute_tool.<name>` span is visible at `/traces` — same demo bar as `/build` (`harness.md` § Done).
Keep the **README accurate**: if the capability adds a command/env var, update and re-run it before claiming
done.

### 5. Record the delta
Append a short entry to the session report (`reports/sessions/YYYY-MM-DD-HHMMSS-<branch>.md`):

```markdown
## Delta: + capability <slug>
- spec:   spec/capabilities/<slug>.md (+ spec/agent.md if a layer flipped ON)
- code:   agent/tools.py @tool <name>   (or: agent/graph.py node / agent/mcp_tools.py)
- eval:   tests/test_<slug>_gate.py — outcome (judge ≥4) + trajectory (expect <name>, forbid <mutating>)
- gate:   pytest tests/test_<slug>_gate.py → exit 0
- traces: execute_tool.<name> span visible at /traces
```
Then commit + push (one action) and open the PR. Productionising (Postgres parity, artifact, deploy) is a
separate step — `/deploy` (`workflows/deploy.md`); this workflow stops at a green demo gate.

## Checklist (all five, in order — skipping any leaves the capability ungated)
1. `spec/capabilities/<slug>.md` written, EARS lines explicit; layer flipped ON in `spec/agent.md` if new.
2. Tool/node generated from the recipe (cheapest layer; mutating gated; external = MCP/OAuth).
3. One outcome + one trajectory assertion per EARS line, in a gate test.
4. Gate run for real → exit 0; `/traces` shows the new span; README still accurate.
5. Delta recorded in the session report; committed, pushed, PR opened.
