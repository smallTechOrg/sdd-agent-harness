# Pattern: Observability & Evals (Layer 9)

Two halves of "can you trust this run?": **observability** records what happened (every LLM + tool step as
an OTel-shaped span → SQLite → a built-in `/traces` viewer, no Docker); **evals** judge whether it was
*right* (OUTCOME + TRAJECTORY), and run as a mechanical gate so a `200` with a wrong answer fails. **Generate
this fresh at build time**, pinning the *current* `opentelemetry-*` packages if you enable OTLP export
(check the latest first — a guessed/old version 404s). The code below is proven working; use it verbatim.

## Observability — spans → SQLite → `/traces`

A span is one timed unit of work. We persist them to the `spans` table (`agent/db.py`: `run_id, name,
kind, attributes(JSON), start_ms, end_ms, duration_ms`) and render them with no JS at `/traces`. The schema
follows the **OTel GenAI semantic conventions** so the same spans can be exported to any OTLP backend later
without renaming. Span names:

| Name | Kind | Wraps |
|------|------|-------|
| `invoke_agent` | `INTERNAL` | the whole run (`agent/runner.py`) |
| `chat <model>` | `LLM` | one model call (`agent/graph.py` agent_node) — also captures `usage_metadata` |
| `execute_tool.<name>` | `TOOL` | one tool call (`agent/graph.py` tools_node) — args + result preview |

### `agent/observability.py` (proven, verbatim)
```python
import time, uuid
from contextlib import asynccontextmanager
from .db import get_sessionmaker, Span

@asynccontextmanager
async def span(run_id: str, name: str, kind: str = "INTERNAL", **attrs):
    """Time a block, capture exceptions, persist one OTel-GenAI-shaped Span row.

    Yields the mutable `attrs` dict so callers can enrich it in-flight, e.g.
        async with span(run_id, f"chat {model}", "LLM") as sp:
            sp["tokens"] = resp.usage_metadata
    """
    start = time.time()
    try:
        yield attrs
    except Exception as exc:                      # record then re-raise — never swallow
        attrs["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        end = time.time()
        async with get_sessionmaker()() as s:
            s.add(Span(
                id=str(uuid.uuid4()), run_id=run_id, name=name, kind=kind,
                attributes=attrs,
                start_ms=int(start * 1000), end_ms=int(end * 1000),
                duration_ms=int((end - start) * 1000),
            ))
            await s.commit()
```
The loop calls this around every LLM and tool step — `patterns/react-agent.md`. The mutable yield is the
whole contract: enrich `sp` in the block (tokens, result preview, args) and it lands in `attributes`.

> **Check the type of `usage_metadata` before reading tokens.** Some providers return a TypedDict
> (plain `dict`); `getattr(u, "input_tokens", 0)` silently returns 0 on a dict. Use
> `u.get("input_tokens", 0) if isinstance(u, dict) else getattr(u, "input_tokens", 0)`.
> See `patterns/react-agent.md` `agent_node` for the canonical pattern.

### The `/traces` viewer lives in `patterns/interface.md`
The `/traces` viewer (server-rendered HTML, no JS, no build step — a timeline of runs, each span with a
kind-color badge, duration bar, attributes, and any error in red) is part of the self-contained
`agent/server.py` recipe in **`patterns/interface.md`**, where `app = FastAPI(...)` is defined alongside
the `/health`, `POST /runs`, and `/traces` routes plus the small HTML render helper. **This recipe owns the
span emission (the `span()` context manager above) + the evals below**; it does not redefine the viewer.
The viewer reads the `spans` rows this recipe writes — `KIND_COLOR` maps the three kinds emitted here:
`INTERNAL` (the top run span), `LLM`, `TOOL`. This *is* the audit trail (incl. MCP calls —
`patterns/tools-and-mcp.md`).

### Opt-in OTLP export (later, off by default)
The viewer needs no infra. When you want spans in an external backend (Grafana/Tempo, Honeycomb, …), add a
`BatchSpanProcessor` + `OTLPSpanExporter` *alongside* the SQLite write, gated on a setting — never instead
of it; the gate reads the `spans` table. Pin the current `opentelemetry-sdk` /
`opentelemetry-exporter-otlp` and set the GenAI resource attributes when you do.

## Evals — outcome + trajectory, run as a gate

Observability shows what happened; **evals decide pass/fail**, fed by the EARS acceptance criteria in
`spec/capabilities/*.md` ("WHEN <trigger> the system SHALL <response>"). Two axes — both required:

- **OUTCOME** (hard gate) — did it produce the right *answer*? An **LLM-as-judge** scores the final answer
  against the capability's EARS criterion on a **0–5 scale** using **explicit `evaluation_steps`** (no vibes —
  the steps are the rubric, so the score is reproducible and inspectable). This catches the
  `200`-with-a-wrong-answer failure that a status check never will. **The judge is itself an LLM**, so the gate
  uses `stable_outcome_eval` — it samples the judge N times and passes on the margin-protected **mean**,
  reporting variance so a flaky borderline verdict is *visible*, never a silent coin-flip. That is what makes
  "exit 0 = right answer" deterministic instead of probabilistic (the competitive soft spot, closed).
- **TRAJECTORY** — did it get there *correctly*? Read back the persisted spans for the run and assert the
  path: the expected tool(s) were called with sane args, **no *redundant* duplicate calls** (the SAME tool
  with IDENTICAL args — a true retry; legitimately repeated tool use, e.g. query-refine or one call per
  resource, is allowed and expected, since `react-agent.md` sizes `max_iterations` for it), **no
  unsafe/mutating tool fired without its gate** (`patterns/guardrails-and-hitl.md`), `finish` called exactly
  once, iterations under the cap. The trajectory check needs **no LLM** — it's a deterministic read of the `spans` table.
  **For a one-capability v1 slice the trajectory check is ADVISORY** (logged, not gate-blocking) — the
  outcome eval is the hard verdict; trajectory becomes a blocking gate once a **second** capability exists and
  there's a real tool-ordering contract to protect against (per the reconciliation decisions). Run it from
  day one for the signal; promote it to blocking with the 2nd capability.

The runtime judge defaults to the same cheap tier as the product (`spec/tech-stack.md`); for a release gate
you may pin a stronger judge — keep that choice in the spec, not hard-coded.

### `agent/evals.py` (build-time recipe — pin current libs)
```python
from .db import get_sessionmaker, Span
from sqlalchemy import select
from .llm import get_model

JUDGE_PROMPT = """You are a strict grader. Score 0-5 how well the ANSWER satisfies the CRITERION.
Work through each evaluation step, then output the final integer score on the last line as `SCORE: <n>`.

CRITERION (EARS): {criterion}
EVALUATION STEPS:
{steps}

GOAL: {goal}
ANSWER: {answer}"""

async def outcome_eval(goal, answer, criterion, evaluation_steps, *, threshold=4):
    """OUTCOME: LLM-judge the answer against one EARS criterion. Returns (passed, score, text)."""
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(evaluation_steps))
    msg = JUDGE_PROMPT.format(criterion=criterion, steps=steps, goal=goal, answer=answer)
    resp = await get_model().ainvoke(msg)          # judge model — cheap tier by default
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    score = next((int(ln.split(":", 1)[1].strip())
                  for ln in reversed(text.splitlines()) if ln.upper().startswith("SCORE:")), 0)
    return score >= threshold, score, text

async def stable_outcome_eval(goal, answer, criterion, evaluation_steps, *, threshold=4, samples=3, margin=0.5):
    """JUDGE STABILITY: the judge is itself an LLM — the same non-deterministic class we mock. Sample it
    N times, pass only if the MEAN clears (threshold - margin), and report variance so a borderline,
    flaky verdict is visible instead of a coin-flip "exit 0". This is what makes "200-wrong fails"
    DETERMINISTIC rather than probabilistic. Returns (passed, mean, scores)."""
    scores = []
    for _ in range(samples):
        _, score, _ = await outcome_eval(goal, answer, criterion, evaluation_steps, threshold=threshold)
        scores.append(score)
    mean = sum(scores) / len(scores)
    spread = max(scores) - min(scores)
    # pass needs the MEAN above a margin-protected bar; a wide spread (unstable judge) is surfaced, not hidden
    passed = mean >= (threshold - margin)
    return passed, mean, {"scores": scores, "mean": mean, "spread": spread}

async def trajectory_eval(run_id, *, expect_tools, forbid_tools=()):
    """TRAJECTORY: deterministic read of the spans table — no LLM. Returns (passed, reasons)."""
    async with get_sessionmaker()() as s:
        spans = (await s.execute(
            select(Span).where(Span.run_id == run_id).order_by(Span.start_ms))).scalars().all()
    tool_spans = [sp for sp in spans if sp.kind == "TOOL"]
    tool_calls = [sp.name.removeprefix("execute_tool.") for sp in tool_spans]
    reasons = []
    for t in expect_tools:
        if t not in tool_calls:
            reasons.append(f"missing expected tool: {t}")
    for t in forbid_tools:
        if t in tool_calls:
            reasons.append(f"forbidden/ungated tool fired: {t}")
    # A REPEATED tool name is legitimate ReAct (query-refine, one call per resource, batch per item) —
    # react-agent.md sizes max_iterations for exactly that. Only flag a TRUE redundant retry: the SAME
    # tool called with IDENTICAL args (same name + same `attributes["args"]`). Never blanket set-equality.
    seen_calls = set()
    for sp in tool_spans:
        key = (sp.name, repr((sp.attributes or {}).get("args")))
        if key in seen_calls:
            reasons.append(f"redundant duplicate call (same tool, identical args): {sp.name}")
        seen_calls.add(key)
    if any("error" in (sp.attributes or {}) for sp in spans):
        reasons.append("a span recorded an error")
    return not reasons, reasons
```
EARS criterion → `criterion`; the capability's acceptance bullets → `evaluation_steps` and `expect_tools` /
`forbid_tools`. One EARS line ⇒ one outcome assertion + one trajectory assertion.

## Gate (this is the gate — run it, don't trust it)
The demo gate runs a **real** agent run, then the **stable outcome** eval (hard) + the trajectory eval
(advisory for a 1-capability slice, blocking once a 2nd capability exists). A passing HTTP status with a
sub-threshold judge mean **fails the gate**. → `workflows/gates.md`.
> **REQUIRES `asyncio_mode = "auto"`** under `[tool.pytest.ini_options]` in the generated `pyproject.toml`
> (`workflows/build.md` §3). Without it, pytest-asyncio's default STRICT mode never awaits this unmarked
> `async def test_*` — it is skipped with a "coroutine never awaited" warning while the suite stays green,
> silently disabling this 200-with-a-wrong-answer guard (the exact false-green the gate exists to stop). The
> same applies to the autouse async DB fixture in `patterns/persistence.md`.
```python
import os, pytest

# KEY GUARD (REQUIRED): this is a REAL run + a REAL LLM judge. Gate check 2 (`uv run pytest`) collects this
# file; the SAME suite also runs in a keyless lane (the deterministic CI half below / any keyless invocation),
# where run_agent → get_model() RAISES `RuntimeError("APP_LLM_API_KEY is required")` and ERRORS collection
# instead of skipping. The skipif turns that into a clean SKIP; with a funded key it runs as the gate's
# in-process check-6 twin.
@pytest.mark.skipif(not os.getenv("APP_LLM_API_KEY"), reason="real run + LLM judge needs a funded key")
async def test_demo_gate():
    run_id = "gate-1"
    GOAL = "How long do refunds take?"
    # DATA-INGEST branch (REQUIRED when a capability is session-scoped — C-SESSION-SCOPE), mirroring
    # demo_gate.sh check 5 and the Playwright journey: a real key is NOT enough — without the resource loaded
    # into the session, the query tool returns "No <resource> loaded", the answer is a non-answer, and the
    # outcome assert below FALSE-REDs a CORRECT agent. So load the fixture into a session and pass session_id:
    #   from agent.sessions import load_resource
    #   sid = "gate-sess-1"
    #   load_resource(sid, open("scripts/fixtures/<resource>.<ext>").read())   # build.md §3 fixture
    #   state = await run_agent(GOAL, run_id=run_id, session_id=sid)
    # For a key-free/own-data agent (no C-SESSION-SCOPE) use the plain form on the next line and delete the above.
    state = await run_agent(GOAL, run_id=run_id)              # real run, real model
    ok_o, mean, detail = await stable_outcome_eval(           # multi-sample judge — deterministic, not a coin-flip
        goal=GOAL, answer=state["answer"],
        criterion="WHEN asked about refund timing the system SHALL state 5 business days.",
        evaluation_steps=["Does the answer mention refunds?",
                          "Does it state 5 business days?",
                          "Is it free of contradicting timelines?"])
    # forbid_tools is checked against recorded execute_tool.* spans; `finish` never emits one (the loop skips
    # it — patterns/react-agent.md), so only list a REAL mutating tool here (e.g. delete_record). [] = none.
    ok_t, reasons = await trajectory_eval(run_id, expect_tools=["search_docs"], forbid_tools=[])
    assert ok_o, f"OUTCOME failed: judge mean {mean} {detail}"   # a 200 with a wrong answer FAILS here
    # 1-capability slice: trajectory is advisory — log it, don't block. Promote to `assert ok_t` at capability #2.
    if not ok_t:
        print(f"TRAJECTORY advisory (not blocking until a 2nd capability): {reasons}")
```
Wire the deterministic trajectory half into CI with no key (drive `run_agent` with the FakeModel from
`patterns/react-agent.md`); the LLM-judge outcome half needs a funded `APP_LLM_API_KEY` and runs in the
demo gate proper.

## Test layers — the FakeModel loop test is necessary, NOT sufficient
The scripted FakeModel loop test (`patterns/react-agent.md`) proves the *mechanics* — the loop runs, spans
land, `force_finalize` fires. It does **not** prove the *product works for a user*. The failure mode it
misses, seen for real: every mechanic-level test green while the actual feature is broken. Three layers above
it close that gap, and every build with a UI ships all three.

- **Capability journey tests** (`tests/test_capabilities.py`) — one per EARS criterion in
  `spec/capabilities/*.md`. Each **ingests real data through the real pipeline** (not mocked) and drives the
  loop with a **context-aware fake model** that *reads the actual tool outputs* to form its answer — so real
  tool results flow through the agent and into the assertions. Assert **both** trajectory (right tools, right
  order) **and** outcome (the answer contains the real data values; any structured field is well-formed). A
  scripted model returning canned text cannot catch a grounding bug; one that reads tool output can.
  ```python
  class ContextAwareFakeModel:               # no API key — but NOT canned: it reacts to real tool results
      def bind_tools(self, tools): return self
      async def ainvoke(self, msgs):
          last = msgs[-1]
          if isinstance(last, ToolMessage):  # a real tool just ran — finish using ITS output
              return AIMessage(content="", tool_calls=[{"name": "finish",
                       "args": {"answer": f"Result: {last.content}"}, "id": "f"}])
          return AIMessage(content="", tool_calls=[{"name": "<your_query_tool>", "args": {...}, "id": "t"}])
  ```
  **`args` MUST satisfy the tool's REQUIRED parameters.** The `{...}` placeholder above is illustrative —
  fill it with real values for every required field of `<your_query_tool>` (e.g. `{"question": "..."}` for a
  `query(question: str)` tool). An empty/placeholder `args={}` makes LangChain's `StructuredTool` raise a
  pydantic `ValidationError`, which `tools_node` catches as a fail-soft tool error (`patterns/react-agent.md`);
  the answer becomes `"tool <name> failed: ValidationError…"` and **every outcome test false-REDs on a correct
  agent**. This mirrors the async-tool/`ainvoke` warning above: supply real args, or give the tool optional
  params with defaults so an empty dict validates.
- **Full-stack contract test** (`tests/test_api_flow.py`) — httpx + ASGI transport, FakeModel, **no key**.
  Exercise the real request/response path the UI depends on and assert **every field the UI consumes is
  present** — not just a `200`. The canonical miss: the backend returned the answer but dropped a structured
  field (a `chart_spec`), every backend test stayed green, and the UI silently rendered nothing. Assert the
  `POST /runs` envelope shape **and** the SSE `done` event shape (answer, run_id, thread_id, + any structured
  payload the client reads).
  > **`ASGITransport` skips the FastAPI lifespan.** The checkpointer is created in the lifespan and stashed on
  > `app.state`; ASGITransport never runs it, so `app.state.checkpointer` is **unset** in this test. The
  > `POST /runs` handler therefore reads it as `getattr(request.app.state, "checkpointer", None)`
  > (`interface.md` / `usage-specs/fastapi.md`) — a bare `request.app.state.checkpointer` raises AttributeError,
  > which `create_run` re-wraps as `api_error("RUN_FAILED")`, so the route returns **500** and every faithful
  > contract test false-REDs (HARDENING-LOG iter 9). With `getattr` the in-process run is single-turn (no
  > short-term memory — fine for a one-shot contract assert). If a test must run the lifespan, wrap the app in
  > `asgi-lifespan`'s `LifespanManager` and pin `asgi-lifespan`.
- **Browser journey test** (`tests/e2e/test_primary_journey.py`) — Playwright against the running app,
  asserting the **post-JS DOM** after the real run (`patterns/interface.md`). This is the demo gate's UI half.

Unit tests verify isolated mechanics; these verify the product. → `workflows/gates.md` (check 1 runs all of them).

**Shared test helpers — import absolutely, not relatively.** Common fixtures (e.g. a `ContextAwareFakeModel`,
a CSV fixture) belong in `tests/helpers.py` imported as `from tests.helpers import ContextAwareFakeModel`.
A **relative** import (`from .helpers import …`) raises `ImportError: attempted relative import with no known
parent package` and makes `uv run pytest` die at **collection** (gate check 2 never starts) unless `tests/` is
a package. The build therefore emits empty `tests/__init__.py` + `tests/e2e/__init__.py` markers **and** sets
`[tool.pytest.ini_options] pythonpath = ["."]` (`workflows/build.md` §3), so absolute `from tests.…` imports
resolve. Standardize on the absolute form across every test file — never `from .helpers`.
