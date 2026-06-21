# Agentic AI Patterns

Reference catalog of patterns for building reliable AI agents. Most production agents
combine 4–8 of these. Patterns marked **[core]** apply to nearly every agent; others are
applied selectively based on the task.

---

## Loop & Reasoning

### ReAct Loop [core]

**Intent:** Interleave reasoning and action — the LLM plans a tool call, the harness
executes it, the result feeds back, the LLM re-evaluates — repeating until a final answer.

**When to use:** Any agent that touches an external provider (DB, API, LLM, file system).
Never build a single-shot pipeline for tasks that need external data.

```
[pre-loop: register tools, load session context into AgentState]
          │
          ▼
plan_action ◄──────────────────────────────────────┐
  │                                                │
  ├──(LLM failure) ──────► handle_error            │
  ├──(FINAL ANSWER) ──────► finalize ──► END        │
  └──(execution plan) ────► invoke_tool ────────────┘
                                │
                                ├──(fatal infra failure) ──► handle_error
                                └──(tool error) ──────────► plan_action  ← self-correction
```

**Rules:**
- `invoke_tool` is the single dispatch point for all external calls
- Never call external providers outside the loop
- Max iterations guard: set a hard ceiling (e.g. 25); emit a structured error if hit
- Tool setup and session loading happen before the loop — not inside nodes

---

### Plan-and-Execute

**Intent:** Separate planning from execution — the agent produces a full step-by-step plan
first, then executes each step, optionally re-planning on failure.

**When to use:** Multi-step tasks where knowing the full plan upfront improves reliability
(e.g. data pipeline, report generation). Not for tasks that require adaptive mid-flight
decisions.

```
plan_task ──► [plan: Step 1, Step 2, Step 3]
                │
                ▼
         execute_step (loop over plan)
                │
                ├──(success) ──► next step
                └──(failure) ──► re-plan or handle_error
```

---

### Chain of Thought

**Intent:** Instruct the LLM to reason step-by-step before answering, improving accuracy
on complex or multi-part problems.

**When to use:** Tasks requiring multi-step reasoning, math, or logical deduction. Add
`"Think step by step."` or a structured `<reasoning>` block to the prompt.

**Rules:** Strip `<reasoning>` blocks before persisting or returning the final answer.
Never trust a CoT answer without the chain — if the chain is absent, re-prompt.

---

### Tree of Thoughts

**Intent:** Generate multiple reasoning branches in parallel, evaluate each, and pursue the
most promising — like beam search over thought space.

**When to use:** Problems with a large solution space where greedy single-path reasoning
often fails (e.g. creative planning, complex debugging). Expensive — use sparingly.

---

### Prompt Chaining

**Intent:** Decompose a complex task into a linear sequence of simpler LLM calls, each
output becoming the next input.

**When to use:** Tasks that naturally decompose sequentially (e.g. extract → summarize →
classify). Use when a single prompt becomes too complex or unreliable.

**Rules:** Each link in the chain must validate its input. A bad intermediate output
propagates silently if unchecked.

---

## Tool & Resource Access

### Tool Registry [core]

**Intent:** Store tool definitions in a registry (DB or config); load them at runtime so
the LLM always sees current, real tool names and schemas.

**When to use:** Any agent with more than 2 tools, or any agent whose tools change between
runs.

```
Tool anatomy:
  name        string   machine-readable identifier
  description string   LLM-facing; explains what the tool does and when to use it
  parameters  schema   JSON Schema of inputs the LLM must supply
  handler     fn       actual implementation; never exposed to the LLM
  category    enum     data | service | compute | internal
```

**Rules:**
- Tool descriptions are prompts — write them for the LLM, not the developer
- Always include the real table/resource name in the tool description at runtime
- Never hardcode tool names in the prompt; load from the registry
- Security boundaries by category:
  - `data`: read-only by default; mutations require explicit `write=true` flag
  - `service`: must validate inputs before dispatching
  - `compute`: sandbox execution; never run user-supplied code unsandboxed
  - `internal`: not exposed to the LLM; called by the harness only

---

### Execution Plan [core]

**Intent:** The LLM returns a structured execution plan (tool name + parameters as JSON)
rather than free text. The harness parses and dispatches it.

**When to use:** Every ReAct loop iteration. The plan is the contract between the LLM and
the harness.

```json
{
  "tool": "query_database",
  "parameters": { "sql": "SELECT ..." },
  "reasoning": "I need the row count before proceeding"
}
```

**Rules:**
- Parse with a schema validator; never eval or exec raw LLM output
- If parsing fails: feed the error back to the LLM as a self-correction opportunity
  (recoverable), not a hard failure
- `reasoning` field is optional but strongly encouraged — aids debugging and logging

---

### Sub-agent as Tool

**Intent:** Expose a specialist sub-agent as a tool callable by a parent agent. The parent
sees it as an opaque function; the sub-agent handles its own internal loop.

**When to use:** When a subtask is complex enough to warrant its own reasoning loop (e.g.
a web-research agent called by a report-writing agent).

**Rules:**
- Sub-agent results must be structured (JSON schema); never raw text
- Sub-agents must not share state with the parent — communicate only through the tool
  call interface
- Set a timeout on sub-agent invocations

---

### Code Interpreter

**Intent:** Give the agent a sandboxed environment to write and execute code as a tool.

**When to use:** Data analysis, computation, file transformation tasks where code is more
reliable than LLM arithmetic.

**Rules:**
- Always sandbox — never execute in the host process
- Capture stdout/stderr and return both to the LLM
- Set a hard execution timeout (e.g. 30s)
- Disallow network access from within the sandbox by default

---

## Self-correction & Quality

### Self-Correction [core]

**Intent:** Feed tool errors back to the LLM as context so it can revise its plan and
retry, rather than failing immediately.

**When to use:** All recoverable errors in a ReAct loop.

```
Error taxonomy:
  Recoverable  → feed back to plan_action:
    - unknown capability / tool not found
    - bad JSON in execution plan
    - tool returned a domain error (no rows found, invalid param)
    - LLM hallucinated a parameter value

  Fatal → handle_error immediately:
    - DB/infra unreachable
    - Auth failure
    - Max iterations exceeded
    - Out of memory / timeout
```

**Rules:**
- Self-correction budget: max 3 correction attempts per tool call before escalating to fatal
- Include the original error verbatim in the correction prompt
- Do not silently swallow errors — always log recovery attempts

---

### LLM-as-Judge

**Intent:** Use a separate LLM call to evaluate the quality or correctness of another
LLM's output.

**When to use:** High-stakes decisions, output validation, ranking multiple candidate
answers, detecting hallucinations.

```
candidate_output ──► judge_prompt ──► {score, verdict, reasoning}
                          │
              (use a different model or system prompt for the judge
               to avoid sycophancy)
```

**Rules:**
- Judge model should differ from generator model (or use a different temperature/prompt)
- Judge output must be structured (score + reasoning), not free text
- Never use the judge's verdict without checking `reasoning` — a confident wrong verdict is
  worse than no verdict

---

### Self-Consistency

**Intent:** Sample the same prompt multiple times, then take the majority answer — reduces
variance for tasks with a single correct answer.

**When to use:** Reasoning tasks with deterministic answers (math, logic, factual lookup)
where single-sample output is unreliable. Not for creative or open-ended tasks.

**Rules:**
- Use temperature > 0 to ensure diverse samples
- N ≥ 3 (odd number prevents ties)
- Expensive — only apply when accuracy matters more than cost

---

## Orchestration

### Orchestrator-Worker

**Intent:** A master agent delegates subtasks to specialist workers, aggregates results,
and synthesizes a final output.

**When to use:** Tasks that decompose into parallel or semi-independent subtasks too
complex for a single ReAct loop.

**Differs from Sub-agent as Tool:** The orchestrator has *intentional awareness* of the
worker topology. Sub-agent as Tool treats workers as opaque calls.

**Rules:**
- Workers must not call back to the orchestrator (no circular delegation)
- Orchestrator owns the final synthesis; workers return data only
- Set a concurrency cap on parallel worker invocations

---

### Router

**Intent:** Classify the incoming request and dispatch to the correct specialist agent or
handler.

**When to use:** A single entry point that must handle multiple distinct task types (e.g.
a chat interface that routes to a data agent, a booking agent, or a FAQ agent).

```
input ──► classify_intent ──► route to specialist
                │
                ├── intent: data_query    ──► data_agent
                ├── intent: booking       ──► booking_agent
                └── intent: faq           ──► faq_handler
```

**Rules:**
- Router classification must be fast and cheap (small model or keyword match)
- Always define a fallback handler for unrecognised intents
- Log the classified intent with confidence score

---

### Multi-agent Debate

**Intent:** Multiple agents with opposing or diverse perspectives each evaluate the same
problem; a synthesizer resolves disagreements into a final answer.

**When to use:** High-stakes decisions where a single agent's blind spots could be
catastrophic (security review, legal analysis, medical triage).

**Rules:**
- Agents must not see each other's outputs during their initial evaluation
- Synthesizer must quote the specific disagreements, not average them away
- Minimum 3 agents; even number can deadlock

---

### Event-driven Agent

**Intent:** The agent is triggered by external events (queue messages, webhooks, cron) and
runs autonomously without a human prompt.

**When to use:** Monitoring, scheduled analysis, reactive automation.

**Rules:**
- Idempotency: processing the same event twice must produce the same outcome
- Dead-letter queue: failed events must be captured, not silently dropped
- Each run is fully isolated — no shared in-memory state between event firings

---

## Memory

### Memory Patterns

**Intent:** Give agents access to information beyond the context window by typing memory
into distinct stores with different lifecycles.

```
Working memory    In the context window (AgentState). Current run only.
Episodic memory   Past runs stored in DB. Retrieved by run_id or recency.
Semantic memory   Vector store. Retrieved by embedding similarity.
Procedural memory Prompts, tool definitions, few-shot examples. Loaded at session start.
```

**When to use:**
- Working: always (it's just AgentState)
- Episodic: when the agent needs to reference what it did in prior runs
- Semantic: when the agent needs to find relevant documents or past interactions
- Procedural: when tool definitions or prompts change between deployments

**Rules:**
- Never load entire episodic history into context — retrieve and summarise
- Semantic retrieval must include a relevance threshold; discard low-score results

---

### RAG (Retrieval-Augmented Generation)

**Intent:** Retrieve relevant documents from an external store and inject them into the
LLM prompt, grounding answers in source material.

**When to use:** Knowledge-intensive tasks where the LLM's training data is stale,
incomplete, or too general.

```
query ──► embed ──► vector_search ──► top-k chunks
                                          │
                                          ▼
                              [system prompt + chunks + query] ──► LLM
```

**Rules:**
- Chunk size matters — too large dilutes signal, too small loses context (256–512 tokens
  is a common starting point)
- Always return source citations with the answer
- Retrieval quality degrades silently — add an eval step to monitor precision/recall

---

### Checkpoint-Resume

**Intent:** Persist agent state at each step so a failed run can resume from the last
successful checkpoint rather than restarting from scratch.

**When to use:** Long-running tasks (> 30s), tasks with expensive external calls, any task
where partial completion has value.

```
start ──► step_1 ──► [checkpoint] ──► step_2 ──► [checkpoint] ──► ... ──► end
                          │
                   (on restart, load last checkpoint and resume from step_2)
```

**Rules:**
- Checkpoint before and after every external call
- Checkpoints must be idempotent — re-running a step from checkpoint must be safe
- Expire stale checkpoints (e.g. > 24h) to avoid unbounded storage growth

---

### Context Window Management

**Intent:** Keep the active context within the model's window limit without losing
information needed for task completion.

**When to use:** Any long-running conversation or multi-step task where history accumulates.

**Strategies (in order of preference):**
1. **Summarise** older turns — replace verbatim history with a rolling summary
2. **Retrieve** only relevant history via RAG instead of loading everything
3. **Truncate** oldest turns if summarisation is too expensive (log what was dropped)
4. **Tier** content by priority: system prompt > task context > tool history > old turns

**Rules:**
- Never silently truncate — log what was dropped and why
- Reserve at least 20% of the window for the model's output
- Measure token counts at runtime; never estimate

---

## Safety & Compliance

### Guardrails

**Intent:** Validate inputs and outputs against safety rules before acting on them.

**When to use:** Any agent exposed to user input, or any agent whose output affects
external systems.

```
user_input ──► input_guardrail ──► agent ──► output_guardrail ──► response
                    │                               │
               (violation)                    (violation)
                    │                               │
              reject + log                    redact + log
```

**Types:**
- Input: topic filtering, prompt injection detection, PII detection
- Output: hallucination check, toxicity filter, PII scrubbing, schema validation

**Rules:**
- Guardrails run synchronously on the critical path — keep them fast (< 100ms)
- Log all violations with the full input/output for audit
- Hard block vs. soft warn: define which violations block and which only alert

---

### Human-in-the-Loop

**Intent:** Pause the agent at defined checkpoints and require explicit human approval
before proceeding.

**When to use:** Irreversible actions (send email, delete data, charge a payment),
low-confidence decisions, high-stakes outputs.

```
agent ──► [approval checkpoint] ──► (approved) ──► continue
                    │
               (rejected / timeout)
                    │
              abort + log reason
```

**Rules:**
- Timeout is a rejection — never auto-approve on timeout
- Show the human exactly what will happen next, not just a summary
- Approval is scoped to the specific action — not a blanket "proceed with everything"

---

### Constitutional AI

**Intent:** Give the agent an explicit set of principles and instruct it to evaluate and
revise its own outputs against them before responding.

**When to use:** Outputs that must comply with ethical, legal, or brand guidelines. Useful
as a lightweight alternative to a full LLM-as-Judge setup.

```
draft_output ──► critique_against_principles ──► revised_output
```

**Rules:**
- Principles must be specific and testable — "be helpful" is not a principle
- Log the critique alongside the output for audit
- Constitutional revision is not a substitute for input guardrails
