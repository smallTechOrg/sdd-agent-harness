---
name: zero-shot-build
description: Turn a zero-shot idea into a perfectly-working, thoroughly-tested, spec-driven agent. One intake round (which also collects the API keys into .env), then the agent-builder builds one phase at a time — autonomous within a phase, with a human testing gate between phases. Also used to add a new capability to an existing agent.
argument-hint: [your idea]
disable-model-invocation: true
allowed-tools: Bash(git*) Bash(gh*)
---

You run the human channel — intake, then the testing gate at every phase boundary — and hand the building off to the **agent-builder** orchestrator. The idea is in `$ARGUMENTS`. **If `$ARGUMENTS` is empty, ask the user in plain text to describe their idea / the problem they want to solve, and WAIT for their free-text reply before doing anything else.** Do NOT load `AskUserQuestion` to solicit, suggest, or pick the idea — the idea must come from the user as their own text. Only once you have the idea do you move to Stage 1 intake. Goal: **one prompt → a perfectly-working, thoroughly-tested agent, one user-testable phase at a time.**

**Autonomy model:** autonomous *within* a phase; a **human testing gate between phases**. Intake is the only interactive SETUP step; after it, agent-builder builds a phase end-to-end without pausing, then returns a test-handoff. You present the handoff, handhold the user through testing, and only proceed to the next phase on the user's go. agent-builder pauses mid-phase only on a hard blocker (e.g. a required key still missing from `.env`).

## Stage 1 — Intake (the only interactive setup step)

Intake runs in **three rounds**. Rounds 1 and 2 are about the idea — what to build and how it should behave. Round 3 collects the technical choices needed to build without interruption. The more specific the user is, the better Phase 1 will impress them. All rounds use `AskUserQuestion`; the API key prompt is the only additional manual step.

**Precondition: you already have the user's idea as their own free text** (from `$ARGUMENTS` or the plain-text prompt above). Never use `AskUserQuestion` to generate or propose the idea itself.

### Round 1 — What is the idea?

1. Acknowledge the idea in one sentence.
2. Load the question tool: `ToolSearch` with query `select:AskUserQuestion`.
3. Ask **4 questions** via `AskUserQuestion`, all `multiSelect: true`. Plain, friendly language — no technical jargon. Pure product questions.

   **Every question and every option must be specific to this idea** — not generic category labels. Read what the user wrote, then write questions and options they will instantly recognise as being about *their* thing. If the idea is "email triage agent", don't ask "what kind of input?" with generic buckets — ask "what makes an email urgent?" with options like "It's from my boss", "It has a deadline", "It mentions a specific project". Think like a product designer, not a requirements collector.

   Four themes to cover (adapt wording and options to the idea):
   - **What it works on** *(4 idea-specific options)* — the data, content, or domain. Be concrete: not "documents" but "emails from my inbox", "CSV exports from our CRM", "Slack threads".
   - **What it produces** *(4 idea-specific options)* — the output or action. Be concrete: not "a summary" but "a one-line verdict I can forward", "a ranked list with reasons", "a draft reply ready to send".
   - **The usage pattern** *(4 options)* — who uses it, how often, in what context. E.g. "Just me, a few times a day", "My whole team, whenever something comes in", "Runs automatically in the background", "Our customers use it directly".
   - **Non-negotiables** *(4 options)* — always offer: "My data can't leave my machine", "It must connect to [something they mentioned]", "Keep costs very low", "None — just build it well".

### Round 2 — Deeper on the idea

4. Read Round 1 answers carefully. Identify the 3–4 most important gaps or interesting tensions in what they selected — things that, unresolved, would force a wrong product decision in Phase 1.
5. Load `AskUserQuestion` again. Ask **3–4 follow-up questions** that dig into the specifics of *what they want*, still no technical questions yet:
   - Each question should surface a concrete product choice that affects the Phase 1 design. E.g. if they said "draft reply ready to send" → "How much should it change the tone? Keep it exactly as I'd write it / Make it more professional / I'll tell you per-reply". If they said "runs automatically" → "What should trigger it? New email arrives / I hit a button / On a schedule / Something else".
   - If Round 1 answers were very sparse (mostly "None" or single selections with no strong signal), ask broader questions to uncover the actual use case before going technical.
   - If Round 1 was detailed and specific, ask tighter follow-ups that resolve the most interesting edge cases.

   **Skip a question if Round 1 already answered it.** Do not ask for information you already have.

### Round 3 — What do we need to build it?

6. Read both idea rounds. Now ask the **technical build questions** — 3–4 total, only genuine blockers:
   - **LLM provider** *(single-select)* — offer: **Anthropic (API key)**, **Gemini (API key)**, **OpenRouter**, **Other**. This drives which key the user sets.
   - **Stack preference** — language, database? ("No preference" → Python + SQLite defaults, documented as assumptions.)
   - **How will they access it?** — web UI, CLI, API, scheduled job. Drives whether to build a frontend.
   - **1 follow-up** from the idea rounds only if something would force a mid-build pause — skip if everything is clear.

7. **API key** (the only manual user step). Read `.env` and check whether the key for the chosen provider is already set (non-empty): `AGENT_ANTHROPIC_API_KEY`, `AGENT_GEMINI_API_KEY`, or `AGENT_OPENROUTER_API_KEY` (for **Other**, ask which env var + base URL). If present and non-empty, skip silently. Only if missing or empty, tell the user to set it in `.env` (from `.env.example`) and wait for confirmation. Never echo, print, paste, or commit a secret value.
8. Synthesize all three rounds into a one-paragraph brief. ("Just build it" → narrow MVP, Python + SQLite defaults, documented as assumptions.)

## Stage 2 — Design + scaffold + build Phase 1 (delegate)

Invoke the **agent-builder** sub-agent once with the brief and the populated `.env`. Tell it to run, in order, and return the **Phase-1 test-handoff**:

- **DESIGN** — spec-writer writes the full spec: vision/capabilities, `spec/architecture.md` (incl. the `## Stack` section), `spec/agent.md` (if a framework is chosen), and the phased plan in `spec/roadmap.md` under "## Phases of Development" (per phase: Goal · independent slices · key surfaces/files · the exact runnable Gate command · how the user tests it).
- **SCAFFOLD** — branch `feature/<slug>-v0.1`, project dirs, `.env.example`, first commit + push, open the PR.
- **BUILD PHASE 1** — fan out generators per independent slice in parallel, gate each slice with qa-auditor, then return the Phase-1 test-handoff and STOP.

Relay only the hard blockers it escalates (e.g. a required key still missing from `.env`).

## Stage 3 — Human testing gate (you own the human channel)

Phase 1 is the smallest working win: real on the one core path, with clearly-labelled non-functional stubs for everything coming later. **Spoon-feed the user: the ONLY things they should ever do by hand are (a) put secrets in `.env` and (b) interact with the running app (click / chat). They must never run a terminal command to test.** So *you* bring the app up and keep it up:

1. **Launch and keep the app serving — don't hand over commands.** Build and start the app yourself in the background (for the skeleton's single-origin model: `cd frontend && pnpm build`, then `uv run alembic upgrade head`, then start the server with `run_in_background: true`), and **leave it running** across the whole gate so the user just opens a link. Start the server from the **project root**, not `frontend/` — the `pnpm build` step above leaves CWD in `frontend/`, and the server's relative SQLite path then fails with "unable to open database file" even though the DB exists. Verify it's actually up before handing off: `curl` the real page and confirm 200 **and** that it renders STYLED (utilities present in the built CSS / non-barebones), per `harness/patterns/tech-stack.md` and the qa-auditor UI rule. Keep the server process alive until the user has finished testing this phase (restart it silently if it dies); only the user's `.env` secrets and their in-app answers are manual.
2. Load the question tool: `ToolSearch` with query `select:AskUserQuestion` (before asking).
3. Hand the user **only a live link and what to look for** — the ready URL (e.g. `http://localhost:8001/app/`), **what to click / type / look at**, the **expected result**, and which parts are **labelled stubs vs real** (so a stub is never mistaken for a bug). No build/run/migrate commands in the handoff — those are already done and running.
4. Ask via `AskUserQuestion`: **"Does Phase 1 work as you expected?"** → options **"Yes — continue to Phase 2"** / **"I hit an issue"**.
5. **On "I hit an issue":** capture what the user saw, then invoke **qa-auditor** to diagnose and CLASSIFY the root cause (SPEC vs CODE, and which surface). Route the fix: SPEC → spec-writer rewrites the spec, then the responsible generator(s) redo the code; CODE → the responsible **code-generator** and/or **code-generator** fixes the surface. Re-gate with qa-auditor, commit + push the fix yourself, then rebuild + restart the running app yourself and **re-present** the gate (still just a live link, no commands). Loop until the user is satisfied.
6. **On "Yes":** proceed to Stage 4.

## Stage 4 — Per remaining phase (build → gate, repeat)

For EVERY remaining phase boundary:

1. Invoke **agent-builder** again — **one phase per invocation** — passing the user's feedback from the prior gate. It wires the relevant stubs into real functionality, fanning out generators per independent slice in parallel and gating each with qa-auditor, then returns that phase's test-handoff and STOPS.
2. Run the **Stage 3 human testing gate** again for this phase.

Repeat until no phases remain.

## Stage 5 — Ship + report

1. **qa-auditor** — final whole-tree drift audit (CLEAN). Route any divergence per Stage 3 and re-verify.
2. **agent-builder** — ensure the final state is pushed and the PR body is current.
3. Summarize for the user: what was built, the **live URL it's running at** (keep it serving), what's deferred, and the PR link. Run commands belong in the README for the record — not as something the user must execute to test.

## Adding a capability to an existing agent

If the spec is already filled in and the user is adding a capability: skip the scope intake; confirm the existing `.env` already holds the needed keys and ask only if the new capability requires a new provider/key. Tell agent-builder to run **spec-writer** (it owns architecture + roadmap now: add the capability to the spec and append an incremental phase to `spec/roadmap.md`, self-reviewed) → fan out the **frontend/backend generators** per slice → gate with qa-auditor. Then run the **human testing gate** on the new phase, same as any other.
