# Harness — Build a production agent from a spec, and prove it ran

**What this harness is:** the only spec-driven harness that **compiles and proves it ran** — every
acceptance criterion is bound to an executable check, and *done* means the agent booted and gave the right
answer: **proven, not documented.** Other tools stop at "the code matches the spec." We don't trust a green
badge or a paragraph that says "it works" — we boot the real agent over HTTP, run a real two-turn
conversation, and **fail a `200` that returns the wrong answer.** That mechanical exit-0 runtime+outcome gate
is our edge. Lead with the proof.

How it works: Claude Code turns a one-line idea into a working, deployable agentic AI agent. The repo gives
you four things — a **spec contract** (what to build), **workflows** (how), **mechanical gates** (proof it
works), and precise **pattern recipes** in `harness/patterns/`. The non-negotiable rules every build inherits
live in one versioned file: [`spec/constitution.md`](../spec/constitution.md) — each MUST there maps to a
gate line, so the constitution is *enforced*, not preached.

---

## Two zones — be honest about what the spec owns

This harness has **two zones**, and which artifact is the source of truth differs between them. Claiming
"pure spec-as-source" end to end would be a lie the repo can't back, so we don't.

- **The tested CORE (code is truth — a version-pinned dependency).** The async server, the ReAct loop
  (`force_finalize` + `max_iterations` sizing + AST-eval action-safety), `config.py`, the `ok()`/`api_error()`
  envelope, session-scoped resources, usage/cost columns, the `/traces` dashboard, the gate harness, the UI
  shell, SQLite + `create_all`. This ships **already tested**. You treat it like any framework dependency:
  the code is authoritative, you configure it — you do **not** regenerate it from a spec. Pinned per-version
  *usage specs* harden the one surface near it that we still generate.
- **The generated DOMAIN (spec is truth).** Capability nodes, tools, prompts (`.md`), the EARS evals, and the
  domain UI screens. Here the spec authors the behavior; `/build` fills only these seams from the recipes.

`/build` reuses the core and **generates only the domain** — everything else is configured, not re-derived.
That is what makes a full UI on every build affordable.

## The spec contract (what the user provides)
Four files, plus the inherited constitution:
- `spec/product.md` — what it does, success criteria, domain instructions, out-of-scope.
- `spec/capabilities/*.md` — one per capability, with EARS acceptance criteria. **Every EARS line carries an
  `[@eval: path::case]` token** binding it to its executable check; a lint fails the build if any criterion is
  unbound. These criteria *are* the eval gate's inputs.
- `spec/agent.md` — which agentic layers are ON (the on/off ledger; every ON layer must trace to a capability).
- `spec/tech-stack.md` — provider, runtime model (cheap tier by default), DB, deploy target, tools.
- `spec/constitution.md` — the versioned MUST/SHOULD list every capability and gate inherits (read it).

## Build — one intake round, then unattended to green
`/build "<idea>"` → intake (4 questions, **API key + runtime model collected at Q4**) → fill the spec →
generate the domain on `feature/<slug>-<date>` → demo gate. After intake the build runs **unattended** to a
green gate — no mid-build "Proceed?", no asking for the key later; self-diagnose from logs + `/traces` first.
Pause only on a true blocker, then ask via `AskUserQuestion` (load it via ToolSearch *before* intake).

The target stack is the frontier baseline: a Deep-Agent ReAct loop on LangGraph, tools (MCP for external
integrations only), memory, observability (OTel spans → a built-in `/traces` dashboard, no Docker), and evals,
behind a tested Next.js UI shell. v1 ships the **thinnest real slice** — one capability fully real, the rest
spec-registered + deterministic + journey-complete stubs — and capabilities are added one at a time.

## Two model roles
**Claude Code** builds it. The **product's runtime LLM** is a separate choice (Anthropic / OpenAI / Google),
defaults to a cheap tier, and is **chosen at intake** and pinned in `spec/tech-stack.md`. The model id must be
current and verified against the provider before pinning (a 404 ≈ a guessed/old model name). The runtime LLM
is never stubbed; other deps may be stubbed in v1 but only if spec-registered, deterministic, and
journey-complete.

## Done = the gate exits 0 (mechanical, two-tier)
"Done" is not an opinion, a badge, or "looks right." **Done = the gate script exits `0`** (`workflows/gates.md`).
- **Demo** (the `/build` finish line): the suite passes (FakeModel inner loop), the server boots on port 8001,
  `/health` 200, **two turns** (Q1 then a follow-up Q2 on the same session) complete over HTTP, the **outcome
  eval passes** (a `200` with a wrong answer **fails**; the judge is multi-sampled with margin so the verdict
  is deterministic), and the run is visible at `/traces`.
- **Productionise (`/deploy`):** everything Demo proves, plus the same suite on Postgres, a portable artifact,
  and a reachable URL — user-invoked.

## Keep it honest
- README commands work exactly as written, every command prefixed with its runner (`uv run …`), run from
  repo root — run them before claiming done. **Never report a test as passing without running it**, and never
  mark complete with any check red.
- Work on a `feature/<slug>-<date>` branch into a PR opened before the first feature commit; `main` is
  boilerplate-only. **Never `git add -A`/`.`** — stage specific files. **Commit and push are one indivisible
  action**; an unpushed commit doesn't exist. Hooks enforce branch + secret rules.
- A funded `APP_LLM_API_KEY` is required for any real run. Treat secrets per the constitution: `SecretStr`,
  read only at the use boundary, never logged/printed, gitignored before the file exists.

## Generated front-ends — one source, mechanically enforced
The slash commands and sub-agents Claude Code actually loads (`.claude/commands/`, `.claude/agents/`) and
`CLAUDE.md` are **generated from `harness/`** by `harness/generate.py` — never hand-edit them. Edit the
source in `harness/workflows/`, `harness/agents/`, then run `python harness/generate.py`. This equivalence
(the rules a user reads == the rules the authors edit) has a **mechanical owner**: `python harness/generate.py
--check` exits non-zero on any stale front-end, and `.githooks/pre-commit` runs it whenever a commit touches
`harness/workflows/`, `harness/agents/`, or `generate.py` — a stale `.claude/` is a build-blocking failure,
not a cosmetic one (it is how the user-invoked `/build` once drifted three iterations behind its source).

Procedures: `workflows/{build,deploy,maintain,spec-new-capability,gates}.md`. Sub-agents: `agents/`.
Non-negotiables: `spec/constitution.md`.
