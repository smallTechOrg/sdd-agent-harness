# Capability: <!-- FILL IN: name -->  ·  Priority: <!-- FILL IN: P1 | P2 | P3 -->

> Copy this file to `spec/capabilities/<slug>.md` (one capability per file). Filled by the **spec-writer**;
> the acceptance criteria below ARE the eval inputs. Contract + procedure: `harness/harness.md`,
> `harness/workflows/spec-new-capability.md`. Leave the `<!-- FILL IN -->` markers until completed.
>
> **Priority (set in the heading above) is load-bearing — `/build` reads it:**
> - **P1** = the ONE real v1 slice. Fully implemented, calls the real runtime LLM, proven live by the outcome
>   eval. Exactly one capability per build is P1.
> - **P2 / P3** = a deterministic, journey-complete, spec-registered **STUB**. It is wired into the graph and
>   reachable end-to-end, but returns a fixed contract instead of doing the real work. The stub still has an
>   `[@eval]` that asserts its **stub contract** (a known shape/sentinel), so the journey stays green and the
>   capability is *registered*, even though it is not yet *verified* against real behavior. Promote one P2/P3
>   to a real implementation per follow-up build (`/spec-new-capability`).
> This is the thin-slice rule: v1 ships one real capability + the rest as honest stubs, never five half-builds.

## What & why
<!-- FILL IN: one paragraph — the user-visible behaviour and how it serves a success criterion in
spec/product.md (name the criterion). One capability = one user-visible behaviour; split it if it needs two.
For a P2/P3 stub, also state in one line what the stub returns until it is promoted. -->

## Acceptance criteria (EARS — these ARE the eval inputs)
<!-- FILL IN: formal EARS — each line is testable and observable, and ENDS with an [@eval] traceability token
binding it to an executable check. The agent authors the token; a non-coder never writes it. The analyze
pre-flight + gate lint FAIL the build if any criterion lacks an [@eval]. Keywords: WHEN = trigger,
WHILE = state, IF...THEN = unwanted condition, the system SHALL = response. For a P2/P3 stub, the [@eval]
asserts the stub contract (the fixed shape/sentinel), not real behaviour. -->
- WHEN <trigger> the system SHALL <observable response>. [@eval: tests/test_<slug>_gate.py::<case>]
- WHILE <state> WHEN <trigger> the system SHALL <response>. [@eval: tests/test_<slug>_gate.py::<case>]
- IF <unwanted condition> THEN the system SHALL <safe response>. [@eval: tests/test_<slug>_gate.py::<case>]

## Tools & layers touched
<!-- FILL IN: cheapest tool layer that works — patterns/tools-and-mcp.md § 3-layer model. Only list a
layer that is (or is now being turned) ON in spec/agent.md; never silently enable one. -->
- tool: <name>  (in-process @tool | MCP for external — `harness/patterns/tools-and-mcp.md`)
- layers: <e.g. retrieval ON — `harness/patterns/retrieval.md`>   # omit if none beyond the base loop

## Evaluation
<!-- FILL IN: feeds the mechanical gate — harness/patterns/observability-and-evals.md. For P1 the outcome eval
runs against the real model; for a P2/P3 stub it asserts the stub contract instead. -->
- outcome evaluation_steps:  # 2–4 rubric bullets the LLM-judge scores 0–5 against (no vibes)
  - <bullet 1>
  - <bullet 2>
- expect_tools: [<tool that MUST fire>]
- forbid_tools: [<a real MUTATING/irreversible tool that must NOT fire ungated>]
  # NOTE: forbid_tools is checked against the recorded execute_tool.* spans (observability-and-evals.md).
  # `finish` never emits a tool span (the loop skips it — patterns/react-agent.md tools_node), so listing
  # `finish` here is a NO-OP that asserts nothing. Only list tools that actually execute (e.g. send_email,
  # delete_record). Leave [] if this capability has no mutating tool to guard.

---

## Worked example (delete when filling in)

# Capability: Answer from the docs  ·  Priority: P1

## What & why
A user asks a question about the product's documentation and gets a grounded answer with no invented facts.
Serves the "accurate, cited answers" success criterion in `spec/product.md`. (Real v1 slice — calls the
runtime LLM and is proven live by the outcome eval.)

## Acceptance criteria (EARS — these ARE the eval inputs)
- WHEN the user asks a question covered by the docs the system SHALL answer using only retrieved passages. [@eval: tests/test_answer_from_docs_gate.py::test_grounded_answer]
- WHILE no passage matches WHEN the user asks the system SHALL say it doesn't know rather than guess. [@eval: tests/test_answer_from_docs_gate.py::test_admits_unknown]
- IF the question requests a destructive action THEN the system SHALL refuse and explain why. [@eval: tests/test_answer_from_docs_gate.py::test_refuses_destructive]

## Tools & layers touched
- tool: search_docs  (in-process @tool — `harness/patterns/tools-and-mcp.md`)
- layers: retrieval ON — `harness/patterns/retrieval.md`

## Evaluation
- outcome evaluation_steps:
  - The answer is supported by the retrieved passages and invents no facts.
  - When nothing matches, the answer admits it doesn't know.
- expect_tools: [search_docs]
- forbid_tools: []   # this read-only capability has no mutating tool to guard. (Do NOT use `finish` here —
                     # it never emits a span, so it asserts nothing. A real example: a write capability with
                     # forbid_tools: [delete_record] proves the destructive path stayed gated.)
