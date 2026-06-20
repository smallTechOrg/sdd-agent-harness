# Pattern: Guardrails & HITL (Layer 7)

Where the agent is kept safe and, for the dangerous few, paused for a human. **Generate fresh at build
time**, pinning the *current* `langgraph` / `langchain` (verify latest — a guessed/old version 404s). The
code below is proven against the loop in `patterns/react-agent.md`.

Two distinct mechanisms, don't conflate them:
- **Guardrails** — synchronous middleware hooks that inspect/transform/reject every input, tool call, and
  output. Always on; the baseline.
- **HITL** — a `interrupt()`/`Command(resume)` pause for a human decision on a *small, dangerous* trigger
  set (money, prod-data writes/deletes, external comms). Earns its place beyond action-safety; not on every
  tool. → `patterns/tools-and-mcp.md` § action-safety boundary draws the same line.

## Guardrails: the middleware model — three hook points
One place each, so a reader knows where every check lives. Each hook is a deterministic layer (regex, an
allowlist, a schema check) optionally followed by a model-based layer (a cheap-tier LLM judge) — **stacked,
deterministic first** (it's free and catches the obvious; the model only sees what survives).

| Hook | Fires on | Catches |
|------|----------|---------|
| `on_input` | the user goal, before the first LLM call | prompt injection, off-policy requests, PII in the prompt |
| `on_tool_call` | every tool call, before it runs | dangerous args, PII leaving in args, off-allowlist tools |
| `on_output` | the final answer, before it returns | PII in the answer, policy violations, leaked secrets |

A hook returns a verdict: `allow` (unchanged), `transform` (redacted/masked payload), or `block` (stop with
a safe message). `transform` is the workhorse — redact and continue beats a hard fail most of the time.

### Code — `agent/guardrails.py` (proven, verbatim)
Deterministic PII layer first; a model-based layer slots in behind it (stub shown — wire a cheap-tier judge
via `get_model` from `patterns/model-and-providers.md`). Every verdict is a span so `/traces` shows what was
caught — `patterns/observability-and-evals.md`.
```python
import re
from dataclasses import dataclass
from .observability import span          # patterns/observability-and-evals.md

# --- deterministic PII layer: detect → redact | mask | hash | block -----------------
PII = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ssn":   re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "card":  re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\b\+?\d[\d -]{7,}\d\b"),
}
# per-type strategy — block is reserved for what must never transit (e.g. card numbers)
STRATEGY = {"email": "mask", "ssn": "hash", "card": "block", "phone": "redact"}

def _mask(s: str) -> str:   # keep shape, hide value: a***@***.com
    return s[0] + "***" + s[-4:] if len(s) > 5 else "***"
def _hash(s: str) -> str:   # stable token, irreversible — joins/audits without the value
    import hashlib; return "pii_" + hashlib.sha256(s.encode()).hexdigest()[:12]

@dataclass
class Verdict:
    action: str                    # "allow" | "transform" | "block"
    payload: str                   # text to use downstream (redacted on transform)
    reason: str = ""

def scan_pii(text: object) -> Verdict:
    """Deterministic redact/mask/hash/block. Accepts any content type — coerces to str first."""
    if isinstance(text, list):   # structured content (list-of-parts) — extract text fields
        text = "\n".join(p["text"] for p in text if isinstance(p, dict) and p.get("type") == "text") or str(text)
    elif not isinstance(text, str):
        text = str(text)
    found, out, blocked = [], text, False
    for kind, rx in PII.items():
        if not rx.search(out):
            continue
        found.append(kind)
        strat = STRATEGY.get(kind, "redact")
        if strat == "block":
            blocked = True
        elif strat == "mask":
            out = rx.sub(lambda m: _mask(m.group()), out)
        elif strat == "hash":
            out = rx.sub(lambda m: _hash(m.group()), out)
        else:                                  # redact
            out = rx.sub(f"[REDACTED_{kind.upper()}]", out)
    if blocked:
        return Verdict("block", "", f"blocked PII: {','.join(found)}")
    if found:
        return Verdict("transform", out, f"redacted PII: {','.join(found)}")
    return Verdict("allow", text)

# --- model-based layer (stacked AFTER deterministic; cheap-tier judge) ---------------
async def model_check(text: str, policy: str) -> Verdict:
    """Optional second layer for what regex can't see (injection, off-policy intent).
    Bind a cheap-tier model with structured output (patterns/model-and-providers.md) returning
    {action, reason}; deterministic-allow text only reaches here, so it's a few cheap calls."""
    return Verdict("allow", text)              # replace stub with the judge per spec/agent.md

# --- the three hooks ----------------------------------------------------------------
async def on_input(run_id: str, goal: str, policy: str = "") -> Verdict:
    async with span(run_id, "guardrail.on_input", "INTERNAL") as sp:
        v = scan_pii(goal)
        if v.action != "block" and policy:
            v = await model_check(v.payload, policy)
        sp["action"], sp["reason"] = v.action, v.reason
        return v

async def on_tool_call(run_id: str, name: str, args: dict) -> Verdict:
    async with span(run_id, f"guardrail.on_tool_call.{name}", "INTERNAL") as sp:
        v = scan_pii(str(args))                # PII must not leak into external tool args
        sp["action"], sp["reason"] = v.action, v.reason
        return v

async def on_output(run_id: str, answer: str, policy: str = "") -> Verdict:
    async with span(run_id, "guardrail.on_output", "INTERNAL") as sp:
        v = scan_pii(answer)
        if v.action != "block" and policy:
            v = await model_check(v.payload, policy)
        sp["action"], sp["reason"] = v.action, v.reason
        return v
```

### Wiring guardrails into the loop
Thin call-sites; the logic stays in `guardrails.py`. → `patterns/react-agent.md` for the nodes.
- **`on_input`** — in `run_agent` (`agent/runner.py`) right after the goal arrives, before building the
  initial state. `block` → short-circuit: persist the run `status="blocked"` with `v.reason`, never call the
  LLM. `transform` → use `v.payload` as the goal.
- **`on_tool_call`** — in `tools_node`, before `tool.invoke(...)`. `block` → append a `ToolMessage` saying
  the call was refused (the model recovers — same fail-soft contract as a tool error,
  `patterns/tools-and-mcp.md`); `transform` → run with the redacted args.
- **`on_output`** — in `finalize_node`, wrapping the chosen `answer`. `block` → return a safe canned
  message; `transform` → return `v.payload`.

## Action-safety validation (the baseline that's always on)
Before any guardrail *judges*, classify the tool. This is the floor below HITL — even with no human
available, an irreversible action must clear a deterministic check:
- **Read-only** → runs freely.
- **Mutating but reversible/idempotent** → run; rely on `on_tool_call` guardrails.
- **Irreversible external side-effect** (money, deletes, sends) → **never fires from a force-finalize or a
  runaway loop**, and either is HITL-gated (below) or is refused. The classification lives next to the tool
  (`patterns/tools-and-mcp.md` § action-safety); guardrails enforce it.

### Code-executing tools: AST-validated eval — NEVER regex dispatch (proven, verbatim)
If a tool runs **LLM-generated code** (a pandas/SQL expression, a calculator, a transform), you cannot
gate it with a regex allowlist of substrings: the LLM emits chained calls (`df.groupby('x').agg(...).reset_index()`)
that a regex can't reason about, and a substring filter is an injection surface (`__import__`, dunder
attribute walks, `().__class__.__mro__`). **Parse it, walk the tree, and `eval` in a sealed namespace.**
The check is: `ast.parse` (rejects syntax errors before they run) → walk every node and reject any
disallowed node type / blocked attribute / out-of-allowlist name → `eval` with an **empty `__builtins__`**
so nothing global is reachable.
```python
import ast

# Safe builtins the expression MAY call — these are injected into the sealed namespace (an empty
# `__builtins__` means even `len`/`sum` are unreachable unless bound here). Add domain-safe ones; never add
# eval/exec/open/__import__.
SAFE_BUILTINS = {"abs": abs, "min": min, "max": max, "sum": sum, "len": len, "round": round, "sorted": sorted}
# allowlist of names the expression may reference (the safe builtins + objects bound at call time, e.g. {"df": df})
ALLOWED_NAMES = frozenset(SAFE_BUILTINS) | frozenset({"df", "pd"})
# attribute/name fragments that must never appear — the dunder + import + fs/process escape hatches
BLOCKED_ATTRS = frozenset({
    "__class__", "__bases__", "__mro__", "__subclasses__", "__globals__", "__builtins__",
    "__import__", "__dict__", "__getattribute__", "eval", "exec", "compile", "open",
    "os", "sys", "subprocess", "socket", "input",
})
# node types the expression grammar permits — anything else (Import, comprehension w/ calls, etc.) is rejected
ALLOWED_NODES = (
    ast.Expression, ast.Call, ast.Attribute, ast.Name, ast.Load, ast.Constant,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Subscript, ast.Slice,
    ast.Index if hasattr(ast, "Index") else ast.Slice,
    ast.List, ast.Tuple, ast.Dict, ast.Set, ast.keyword,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.USub, ast.UAdd, ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
)

def safe_eval(expr: str, names: dict):
    """Validate then evaluate an LLM-generated expression. Raises ValueError on anything unsafe — the
    caller turns that into a fail-soft ToolMessage so the model can recover (never a process crash)."""
    try:
        tree = ast.parse(expr, mode="eval")          # syntax-reject before any evaluation
    except SyntaxError as e:
        raise ValueError(f"unparseable expression: {e}")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ValueError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRS:
            raise ValueError(f"blocked attribute: {node.attr}")
        if isinstance(node, ast.Name):
            if node.id in BLOCKED_ATTRS:
                raise ValueError(f"blocked name: {node.id}")
            if node.id not in ALLOWED_NAMES and node.id not in names:
                raise ValueError(f"name not in allowlist: {node.id}")
    ns = {**SAFE_BUILTINS, **names}                          # only the safe builtins + caller objects are visible
    return eval(compile(tree, "<safe_eval>", "eval"), {"__builtins__": {}}, ns)  # sealed: no real globals
```
Wire it inside the tool body (`patterns/tools-and-mcp.md`), passing the live objects as `names`
(e.g. `safe_eval(code, {"df": session_df, "pd": pd})`). The allowlists are the contract — widen
`ALLOWED_NAMES` for your domain, never widen `BLOCKED_ATTRS` open. A `ValueError` returns a fail-soft
`ToolMessage` (same contract as any tool error) so the model retries with a safer expression.

## HITL: pause for a human via `interrupt()` + a persistent checkpointer
HITL is **not** a guardrail variant — it suspends the graph mid-run, persists full state, and resumes on a
human decision that may arrive minutes or hours later. That durability is mandatory: **HITL requires a
persistent checkpointer** (`AsyncSqliteSaver` local → Postgres in prod). A process restart between pause and
approval must not lose the run. → `patterns/durability.md` for the checkpointer setup; `patterns/react-agent.md`
for `AgentState`.

### Trigger set (small, explicit — not every tool)
Gate only: **money** (charge/refund/transfer), **prod-data writes/deletes**, **external comms** (email/SMS/
post on the user's behalf). Everything else runs un-paused — a HITL prompt on a read is just friction.
Define the set in `spec/agent.md`; the tool carries a `requires_approval` marker.

### Code — `agent/hitl.py` (the approval gate inside `tools_node`)
`interrupt(payload)` suspends the graph and surfaces `payload` to the caller; the run resumes when the
client calls the graph again with `Command(resume=<decision>)`. State is held by the checkpointer, so the
resume can be a *different* process. Pin current `langgraph` before generating.
```python
from datetime import datetime, timezone
from langgraph.types import interrupt
from .observability import span          # patterns/observability-and-evals.md
from .tools import TOOL_MAP

REQUIRES_APPROVAL = {"charge_card", "send_email", "delete_record"}   # the trigger set (spec/agent.md)

async def guarded_invoke(run_id: str, name: str, args: dict):
    """Run a tool; if it's in the trigger set, interrupt for a human decision first.
    Resume value contract: {"approved": bool, "reason": str, "by": str}."""
    tool = TOOL_MAP.get(name)
    if name not in REQUIRES_APPROVAL:
        return tool.invoke(args)

    async with span(run_id, f"hitl.request.{name}", "INTERNAL", args=args) as sp:
        sp["status"] = "awaiting_approval"
    # interrupt() persists state via the checkpointer and yields control to the client.
    decision = interrupt({
        "type": "approval_request", "tool": name, "args": args,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "prompt": f"Approve {name}({args})? respond approved|rejected with a reason.",
    })
    approved = bool(decision.get("approved"))
    async with span(run_id, f"hitl.decision.{name}", "INTERNAL",
                    approved=approved, by=decision.get("by", "unknown"),
                    reason=decision.get("reason", "")) as sp:
        sp["status"] = "approved" if approved else "rejected"   # ← persisted audit log row
    if not approved:
        return f"action '{name}' was rejected by a human: {decision.get('reason','no reason given')}"
    return tool.invoke(args)
```
In `tools_node`, route trigger-set tools through `guarded_invoke(...)` instead of `tool.invoke(...)`; all
other tools are unchanged (`patterns/react-agent.md`). Compile the graph **with** the checkpointer and run
with a stable `thread_id` so the resume finds the paused state:
```python
graph = build_graph(model).compile(checkpointer=checkpointer)   # patterns/durability.md
cfg = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
```

### Async approval channel — server side (`agent/server.py`)
A paused run returns an `__interrupt__` payload from `ainvoke`; the approver answers later via a second
endpoint that resumes with `Command(resume=...)`. → `harness.md` for the FastAPI/SSE shape.
```python
from langgraph.types import Command

@app.post("/runs/{run_id}/decision")
async def decide(run_id: str, body: dict):
    """Async approval channel: resume a paused run with a human decision."""
    cfg = {"configurable": {"thread_id": run_id}}
    result = await graph.ainvoke(Command(resume={
        "approved": bool(body.get("approved")),
        "reason": body.get("reason", ""),
        "by": body.get("by", "operator"),
    }), config=cfg)
    return {"run_id": run_id, "status": "resumed", "answer": result.get("answer")}
```

### Timeout auto-reject
A pending approval can't block forever (a paused run holds a thread/quota and may gate money). The poller or
a sweep job auto-rejects on expiry — **fail closed**: no response by the deadline = rejected, never
auto-approved.
```python
# in a periodic sweep (cron/background task) — fail closed on stale approvals
DEADLINE_S = 3600
async def expire_pending(run_id: str, requested_at: datetime):
    if (datetime.now(timezone.utc) - requested_at).total_seconds() > DEADLINE_S:
        await graph.ainvoke(Command(resume={
            "approved": False, "reason": "approval timed out", "by": "system",
        }), config={"configurable": {"thread_id": run_id}})
```

### Audit log
The `hitl.request.*` / `hitl.decision.*` spans **are** the audit trail — who, what args, approved/rejected,
why, when — persisted to the `spans` table and rendered at `/traces`. Same record as MCP audit
(`patterns/tools-and-mcp.md` § MCP security). No second logging system; the span store is the source of
truth. → `patterns/observability-and-evals.md`.

## Mandatory mechanics (do not omit)
- **Deterministic before model-based** — the cheap regex/allowlist runs first; the LLM judge only sees what
  survived (free pre-filter, fewer judge calls).
- **`transform` over `block`** where safe — redact/mask/hash and continue beats a hard fail.
- **HITL needs a persistent checkpointer** — `interrupt()` without durable state loses the run on restart.
- **Trigger set is small and explicit** — money / prod-data writes-deletes / external comms only; gating
  reads is friction, not safety.
- **Fail closed on timeout** — no decision by the deadline = rejected.
- **Every verdict + decision is a span** — guardrails and HITL are auditable at `/traces`, no parallel log.

## Gate (the test that proves it — run it, don't trust it)
No key needed; drive the loop with the scripted `FakeModel` (`patterns/react-agent.md`).
- **Guardrails:** feed a goal/answer with a card number → assert `on_output` returns `block`; feed an email
  → assert `transform` and the address is masked in the payload; assert a `guardrail.*` span was recorded.
- **AST safe-eval** (if a code-executing tool exists): `safe_eval("df.groupby('x').sum()", {"df": df})`
  returns a real result; `safe_eval("__import__('os').system('id')", {})`, `safe_eval("().__class__.__mro__", {})`,
  and `safe_eval("open('/etc/passwd')", {})` each raise `ValueError` — proving the allowlist + blocked-attrs
  + empty-`__builtins__` actually seal the namespace, not a regex that a chained call slips past.
- **HITL:** script the fake model to call a trigger-set tool; assert `ainvoke` returns an `__interrupt__`
  (the run paused, the tool did **not** run); resume with `Command(resume={"approved": False, ...})` →
  assert the tool body never executed and a rejection reason reached the model; resume a second run with
  `approved=True` → assert the tool ran. Use an in-memory/temp checkpointer so the suite needs no live
  approver. Assert `hitl.request.*` and `hitl.decision.*` spans exist (the audit log). → `workflows/gates.md`.
