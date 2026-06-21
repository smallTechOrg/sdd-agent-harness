# AI Agent Rules

**These rules apply to every AI coding session in this repo — Claude Code, GitHub Copilot, Cursor, or any other AI assistant.**

Read this file completely before doing anything else.

---

## ⚠ Non-Negotiable Rules

These rules are never optional, never skipped, and must survive context compression. If your context window is compressed and you can only remember a few rules, these are the ones.

1. **README must always be accurate.** Every command in the README must work exactly as written, from the directory stated. Before ending any session or marking any phase complete: run the README commands yourself — if any fail, fix the README first. A README that lies is worse than no README.

2. **Never claim a test passed if you didn't run it.** "It should work" is not a passing test. Run `pytest` (or equivalent). Show the output. If you can't run it, say so — do not fabricate results.

3. **All commands in docs use the package manager prefix.** For Python + uv projects: every `alembic`, `pytest`, `python` command in the README and docs must be prefixed with `uv run`. Bare commands (e.g. `alembic upgrade head`) fail unless the venv is manually activated — which users won't do.

4. **Working directory must be explicit.** Any README or doc section with shell commands must state the exact working directory at the top of the code block. "Run from project root" is not enough — give the exact relative path from the repo root.

5. **No SQLite substitute for PostgreSQL tests.** If the production database is PostgreSQL, tests run against PostgreSQL. Tests that only pass on SQLite do not count as passing.

6. **Golden-path UI smoke test is mandatory before Phase 2 passes.** If the project has any UI or HTTP surface, Phase 2 must include an automated test that walks the full primary user journey via `TestClient` (or equivalent) and asserts **response content**, not just status codes. See `spec/engineering/workflows/golden-path-smoke-test.md`. A build that returns 200 but renders a broken-looking page is a failing build.

7. **Stub / offline providers must be clearly signalled in the UI.** If an LLM provider is stubbed (no key, demo mode), the UI must display a visible banner on every page. Silent stubs that look like real output are a bug — users will report "it didn't work." The provider should auto-select real when an API key is present (`provider=auto` → real when key set, stub otherwise). Never require the user to flip a flag *in addition* to setting the key.

8. **Stub LLM outputs must be distinct per pipeline node and article-shaped.** Pipeline nodes that share a stub provider must inject unambiguous tags (e.g. `<node:plan>`, `<node:draft>`, `<node:title>`) into their prompts, and the stub must branch on those tags — never on prose keywords from the prompt body (keyword matching cross-contaminates: the word "outline" in a draft prompt must not cause the stub to emit outline bullets instead of a draft). Stub "draft" output must contain paragraphs/headings, not just bullets, so offline demos are credible.

9. **Data-access agents must use a ReAct loop — never a "sample and guess" pipeline.** If the agent's job is to answer questions about external data (CSV files, databases, APIs, file systems), it must generate executable actions (SQL, API calls, file reads), run them against the **full** data, and feed results back to the LLM iteratively until the LLM signals a final answer. A pipeline that passes a sample of data to the LLM and expects a single-shot answer will produce wrong results at scale and must be redesigned before Phase 2 is marked complete. The correct pattern — load → plan action → execute action → observe result → loop until done — must be specced in `07-agent-graph.md` before any code is written. See Section 10 of this file for the full pattern.

10. **Every commit must be pushed immediately.** `git commit` and `git push` are a single atomic action — never one without the other. Use `git commit -m "..." && git push origin <branch>` as a single command. A commit that is not pushed does not exist as far as the project is concerned. This is not optional and is not context-compression-safe — if you remember only this sentence: **commit then push, every time, no exceptions.**

11. **`main` is boilerplate-only. Never commit application code to `main`.** All application code lives on a named feature branch and reaches `main` only via a reviewed pull request. This rule has no exceptions:
    - Before writing any application code, create a feature branch: `git checkout -b feature/<slug>-v0.1`
    - All phase commits go to the feature branch, never to `main`
    - Spec/engineering/boilerplate improvements (no app code) are the only commits that may go directly to `main`
    - When the build is complete, open a PR from the feature branch into `main` — do not merge locally
    - If you find yourself on `main` while writing application code, stop immediately, create the feature branch, and continue there

12. **A PR must exist before the first feature-branch commit, and every push must go to that PR.** After creating the feature branch and pushing the first commit, immediately open a PR: `gh pr create --base main --head feature/<slug>-v0.1`. Every subsequent `git push` automatically updates the same PR — no extra step needed — but the PR must be open. Pushing commits without an open PR is equivalent to committing without pushing: the work is invisible and unreviable. This is not optional and survives context compression.

---

## 1. Session Start Checklist

Complete all steps in order before writing any code:

- [ ] Read `spec/product/01-vision.md` — know what you're building
- [ ] Check if the spec is complete (no `<!-- FILL IN -->` markers in product spec files)
  - If incomplete: surface the agent-builder to the user; do not write application code
- [ ] If spec is complete: read the full spec manifest in `CLAUDE.md`
- [ ] Run `git status` — working tree must be clean before starting
- [ ] **Create and switch to a feature branch**: `git checkout -b feature/<slug>-v0.1` — **never build on `main`**
- [ ] **Create the project directory** `<agent-slug>/` if it doesn't exist — never write agent code into the boilerplate root
- [ ] Open a session report: `<agent-slug>/reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` — **must exist before Phase 1 starts**
  - Use the template in `spec/engineering/workflows/session-report.md`
- [ ] Confirm which phase you are implementing (see `spec/engineering/phases.md`)

## 2. Session Report (Mandatory)

Every session must have a report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md`.

Minimum required sections:
- **Goal:** What this session is trying to accomplish
- **Phase:** Which implementation phase
- **Steps completed:** Logged as you work (not reconstructed at the end)
- **Prompt log:** Every user message and a one-line summary of your action
- **Next steps:** What remains

Update the report in real time. Do not reconstruct it from memory at the end.

## 3. Gate Law

The goal is: **one prompt → working skeleton in ~10 minutes.** All decisions are captured upfront and approved once. There is exactly one user approval gate before code is written.

```
INTAKE (4 questions: scope, stack, trigger, constraints)
        ↓
DRAFT (spec + tech design + plan produced together)
        ↓
ONE APPROVAL (user sees everything at once — one response to proceed)
        ↓
BUILD (Phase 1 → Phase 2, each gated by passing tests)
```

**Rules that never change:**
- Stack decisions (database, language, hosting) belong to the user — captured at intake, never chosen autonomously
- No code is written before the single approval gate is cleared
- Each build phase must pass its gate test before the next phase starts
- Reviewers (spec-reviewer, plan-reviewer) run as background validation and surface blockers, but do not add approval rounds for v0.1

**After v0.1 is running**, subsequent phases follow the standard gate:
```
[Phase implemented] → [gate test passes] → [committed] → [next phase]
```

---

## 4. Spec-First Rule

**No code change without a spec backing it.**

If you are asked to implement something not in the spec:
1. Stop
2. Tell the user what spec gap you found
3. Propose adding it to the spec first
4. Wait for approval before writing code

See `spec/engineering/spec-driven.md` for full details.

## 5. Phase Discipline

**Never start phase N+1 while phase N is incomplete or failing.**

Each phase ends when:
- All code for that phase is written and committed
- All tests for that phase pass
- The qa-auditor sub-agent has signed off (or you have run the QA checklist manually)

See `spec/engineering/phases.md` for the phase definitions and gates.

## 6. Git Discipline

- Commit every logical unit of work — never let the working tree stay dirty for more than one logical change
- **Push immediately after every commit** — treat `git commit -m "..." && git push origin <branch>` as a single indivisible command. Never leave a commit unpushed.
- Commit message format: `phase-N: [what you did]` (e.g., `phase-1: add domain models`)
- Never commit secrets (API keys, passwords, tokens)
- Never force-push without user confirmation
- **Never `git add -A` / `git add .`** — always stage specific files or directories. `-A` sweeps in untracked leftovers from prior build attempts (stray packages, abandoned experiments) and poisons the commit. If a phase needs many files, list them explicitly or stage directories one at a time.

**Before every reply to the user:**
1. Run `git status`
2. If dirty: commit the changes with `git commit -m "..." && git push origin <branch>`
3. Confirm the working tree is clean **and** the branch is pushed before replying

## 7. Test Before Claiming Done

A phase is not done until tests pass. "It looks right" is not a test.

- Write tests for each capability as you implement it
- Run the full test suite before marking a phase complete
- If tests fail, fix them before moving on

## 8. Error Resilience

Every external call (API, database, LLM) must have:
- Error handling that doesn't crash the agent
- Logged failures (to file or stdout at minimum)
- Graceful degradation (the agent continues if a non-critical step fails)

## 9. No Gold-Plating

Build what the spec says, nothing more.

- No extra features "while you're in there"
- No refactoring outside the current phase scope
- No premature abstractions
- If you spot a future improvement, add it to `reports/sessions/[current].md` under "Future improvements" and keep moving

## 10. Agent Loop Design Patterns

### When to use a ReAct loop

Use a ReAct (Reason + Act) loop whenever the agent needs to interact with external data to answer a question. This covers:

- Data analysis over CSV / database tables
- Web search agents that need to look up facts
- File system agents that browse or read files
- API agents that call external services

**Never** design a single-shot pipeline for these cases ("pass a sample to the LLM and return whatever it says"). Single-shot answers are wrong for any dataset larger than the sample, and cannot self-correct.

### The canonical ReAct loop shape

```
START
  │
  ▼
load_data          ← load full data into queryable form (in-memory SQLite, index, etc.)
  │
  ▼
plan_action ◄───────────────────────────────────┐
  │                                             │
  ├──(error / LLM failure) → handle_error       │
  │                                             │
  ├──(FINAL ANSWER signal) → finalize → END     │
  │                                             │
  └──(action returned) → execute_action ────────┘
                              │
                              ├──(hard error: non-recoverable) → handle_error
                              │
                              └──(SQL/API error: feed back to LLM for self-correction)
```

### Termination protocol (mandatory)

The LLM must have an unambiguous way to signal it is done. Define this in the spec before writing code:

```
FINAL ANSWER: <the complete answer text here>
```

The `plan_action` node checks if the LLM response starts with `FINAL ANSWER:` (case-insensitive). If yes, strip the prefix and route to `finalize`. If no, treat the response as the next action to execute and loop.

This is not optional — without a termination signal, the loop runs until max iterations.

### Max iterations guard (mandatory)

Every ReAct loop must have a configurable ceiling:

```python
max_agent_iterations: int = Field(default=10)
```

After `execute_action` increments `iteration_count`, check:
```python
if iteration_count >= max_iterations:
    return {**state, "error": f"Max iterations ({max_iterations}) reached"}
```

Route to `handle_error`. Never let a loop run unboundedly.

### Self-correction on action errors

When an action fails (e.g. SQL syntax error, API 4xx, file not found), **do not immediately fail the pipeline**. Instead:

1. Append the failed action and its error message to `action_history` in state, flagged as `is_error: True`
2. Increment `iteration_count`
3. Route back to `plan_action`

The prompt for the next `plan_action` call shows the error inline:

```
[2] SQL: SELECT MIN(x) FROM data GROUP BY region
    Error: misuse of aggregate function MIN()
    → This query failed. Please write a corrected SQL query.
```

The LLM sees the error and writes a corrected action.

**Recoverable — feed back and loop:**
- SQL syntax or runtime errors (let the LLM rewrite the query)
- Malformed or non-JSON LLM response (ask the LLM to reformat its output)
- Unknown capability name (tell the LLM the valid capability list; see Section 11)
- Non-SELECT SQL attempt on a read-only tool (remind the LLM the constraint; ask for SELECT)
- Tool parameter validation failure (show the parameter schema; ask the LLM to retry)

**Fatal — route to `handle_error` immediately:**
- Max iterations reached
- LLM call itself fails (network error, 5xx)
- Infrastructure failure in tool executor (DB connection dropped, file missing, credentials revoked)

The key principle: **if the LLM could correct the mistake given better information, feed back and loop. Only fail when the environment itself is broken.**

### In-memory data cache pattern

When the agent loads data at the start of a run (CSV → SQLite, documents → vector index, etc.), the connection or index object is not serializable and cannot live in `AgentState`. Use a module-level dict keyed by `run_id`:

```python
_db_cache: dict[str, sqlite3.Connection] = {}

def _cleanup_db(run_id: str) -> None:
    conn = _db_cache.pop(run_id, None)
    if conn:
        conn.close()
```

- `load_data` creates the resource and stores it: `_db_cache[state["run_id"]] = conn`
- `execute_action` reads it: `conn = _db_cache.get(run_id)`
- `finalize` and `handle_error` both call `_cleanup_db(run_id)` in a `finally` block

This guarantees the resource is cleaned up whether the pipeline succeeds or fails.

### Action history in AgentState

The running log of actions and their results must live in state so the full context is available to the LLM on every `plan_action` call:

```python
class AgentState(TypedDict, total=False):
    ...
    action_history: list[dict]  # [{"action": str, "result": str, "is_error": bool}]
    iteration_count: int
    llm_response: str           # raw last LLM output — router inspects this for FINAL ANSWER
```

Persist `action_history` to the database as JSON so it can be displayed in the UI (the "Agent reasoning" trace).

### What to spec in 07-agent-graph.md before writing code

Before writing any node code, `07-agent-graph.md` must answer:

1. What action type does the LLM generate? (SQL, HTTP request, file path, etc.)
2. What is the exact FINAL ANSWER signal string?
3. What constitutes a recoverable action error vs a fatal error?
4. What is the max iterations default?
5. How is the in-session data store created and cleaned up?
6. What fields does `AgentState` carry for history and iteration count?
7. **What tools does the agent have access to?** — name, type, capabilities, and parameter schemas for every tool. (See Section 11 — Tool Registry.)
8. **What is the exact LLM tool invocation format?** — the JSON shape the LLM must produce to call a tool.
9. **What triggers tool registration?** — the user action (file upload, API key entry, etc.) that creates a Tool record in the DB.

If any of these are missing from the spec, raise a blocker before Phase 2 starts.

---

## 11. Tool Registry and Capability Dispatch

A **Tool** is a named, typed, executable unit that the LLM can invoke during the ReAct loop. Every external interaction the agent performs — querying a data source, calling an API, sending a message, reading a file — must be modelled as a Tool. This section defines the standard Tool abstraction and the patterns for registering, loading, and dispatching tools.

### Tool anatomy

Every tool has the same structure:

```
Tool
  ├── id           — unique identifier (UUID)
  ├── name         — snake_case label shown to the LLM (e.g. "csv_query", "weather_api")
  ├── type         — implementation type that determines which executor runs it
  ├── description  — one sentence shown to the LLM in the planning prompt
  ├── config_json  — type-specific runtime config (table name, base URL, credentials ref, etc.)
  └── capabilities — one or more named actions the tool exposes
        └── Capability
              ├── name              — the callable action (e.g. "run_query", "get", "send")
              ├── description       — shown to the LLM
              └── parameter_schema  — JSON Schema dict describing the parameters
```

Store Tool and Capability records in the application database. Do not hardcode them in the agent source.

### Tool categories

| Category | Example types | When to use |
|---|---|---|
| **Data source** | `csv_query`, `sql_query`, `vector_search`, `graphql_query` | Agent reads or queries external data |
| **External action** | `http_request`, `send_email`, `post_webhook`, `write_file` | Agent affects the outside world |
| **Compute** | `python_eval`, `shell_exec` | Agent runs calculations or scripts (sandbox required) |

A single ReAct loop can call tools from multiple categories in the same session.

### Tool Registry pattern

Tools are created when a user connects a resource — not at agent startup. The registration flow is:

```
User connects a resource
(uploads CSV, provides API endpoint, enters credentials, etc.)
       ↓
System creates a Tool record (name, type, description, config)
       ↓
System creates Capability records (one per action the tool exposes)
       ↓
Tool is available to any session that includes this resource
```

The `load_data` node loads all Tool + Capability records for the current session from the DB at run start. This lets the agent discover its available tools at runtime — no hardcoded tool list in agent code.

`AgentState` must carry the loaded tools list:

```python
tools: list[dict]  # [{"name", "type", "config", "capabilities": [{"name", "description", "parameter_schema"}]}]
```

### LLM tool invocation format

Define exactly one invocation format in `07-agent-graph.md` before writing any node code. The recommended shape:

```json
{"tool": "csv_query", "capability": "run_query", "parameters": {"query": "SELECT ..."}}
```

When the session has only one tool, `tool` may be omitted for brevity — but include it whenever there are multiple tools so the LLM is explicit. The `plan_action` prompt must show the LLM the exact format to use, with an example.

### Capability dispatch in execute_action

`execute_action` dispatches by **tool type**, not by capability name. Multiple tool types can expose a capability with the same name (e.g. both `csv_query` and `sql_query` can expose `run_query`):

```python
def execute_action(state):
    # 1. Parse LLM response — bad JSON is recoverable
    try:
        call = json.loads(state["llm_response"])
    except json.JSONDecodeError as e:
        return _loop_back(state, error=f"Response was not valid JSON: {e}. Respond with a JSON object only.")

    capability_name = call.get("capability")
    parameters = call.get("parameters", {})

    # 2. Find the tool that exposes this capability — unknown capability is recoverable
    tool = _find_tool_for_capability(state["tools"], capability_name)
    if tool is None:
        valid = [cap["name"] for t in state["tools"] for cap in t["capabilities"]]
        return _loop_back(state, error=f"Unknown capability '{capability_name}'. Valid options: {valid}")

    # 3. Dispatch by tool type
    match tool["type"]:
        case "csv_query":
            result = _execute_sql(state["run_id"], parameters.get("query", ""))
        case "http_request":
            result = _execute_http(tool["config"], parameters)
        case "send_email":
            result = _execute_email(tool["config"], parameters)
        case _:
            # Fatal — no executor registered for this type
            return _error(state, f"No executor registered for tool type '{tool['type']}'")

    return _loop_back(state, capability=capability_name, parameters=parameters, result=result)
```

`_loop_back` appends the result (or error) to `action_history`, increments `iteration_count`, checks the max-iterations guard, and returns the new state. It never raises — it always returns a valid state dict.

### Prompting the LLM about available tools

The `plan_action` prompt must list every available tool and capability clearly. Format each tool as a block the LLM can scan:

```
Available tools:

Tool: csv_query  — Execute SQL SELECT queries against the uploaded dataset.
  Capability: run_query
    Description: Run a SQL SELECT against the data table.
    Parameters:
      query  (string, required)  — A valid SQL SELECT statement. Table name: 'sales_2024'.

To use a tool, respond with exactly this JSON (no prose, no markdown fences):
{"tool": "csv_query", "capability": "run_query", "parameters": {"query": "..."}}

When you have enough information to answer the user's question, respond with:
FINAL ANSWER: <your complete answer here>
```

Key rules for the tool prompt block:
- List tool name, type description, and every capability with its parameter schema
- Show the **exact** invocation JSON — do not leave the format ambiguous
- Put the FINAL ANSWER signal on the same page so the LLM sees both together
- For multi-source sessions, include the real table name (or endpoint) for each tool, not a generic placeholder

### Multi-tool sessions

When a session has multiple tools (two CSVs, a CSV + an external API, etc.):
- The `load_data` node loads all tools and their capabilities into `state["tools"]`
- The planning prompt lists all of them
- The LLM may call tools in any order and combine results across iterations
- `execute_action` resolves the `tool` field from the LLM response against the `state["tools"]` list; if `tool` is missing, scan all tools for the named capability

The agent can JOIN results across tools by accumulating intermediate results in `action_history` and referencing them in later iterations.

### Security boundaries (non-negotiable)

- **Data source tools:** Enforce read-only at the executor level. Any non-SELECT SQL must be rejected as a recoverable error — never passed to the database. Log every rejection.
- **External action tools** (`send_email`, `post_webhook`, `write_file`): Require explicit user opt-in in the UI before the session starts if the action is irreversible. Log every execution with its parameters.
- **Compute tools** (`python_eval`, `shell_exec`): Require a sandboxed executor. Never enable by default. Explicitly excluded from v0.1 scope unless the spec requires them.

---

## 12. When Stuck

If requirements are unclear:
1. Stop
2. List your specific questions in the session report
3. Ask the user — do not guess

If the spec is ambiguous:
1. State the ambiguity
2. Propose an interpretation
3. Wait for confirmation before implementing

## 13. Closing a Session

Before ending a session:
- [ ] Working tree is clean (all changes committed and pushed)
- [ ] Session report is complete and up to date
- [ ] Tests pass
- [ ] `README.md` updated if project layout, setup steps, or commands changed
- [ ] Note which phase you're on and what comes next in the session report
