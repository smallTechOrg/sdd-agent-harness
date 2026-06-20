---
marp: true
theme: default
paginate: true
size: 16:9
---

# Spec-Driven Development & Agentic Harnesses
## our choices vs the field vs academic rigor

A working tour of how AI-coded systems keep **intent** and **implementation** from diverging — and where our harness lands among OpenSpec, GitHub Spec Kit, AWS Kiro, and Tessl.

*Audience: engineers deciding how to structure spec ↔ code for AI-built agents.*

---

## Why this deck exists

**Educate before we decide.** We are about to make architectural commitments (spec format, who-wins-on-conflict, the build loop). Those are expensive to reverse. This deck front-loads the field so the decisions are informed, not default.

- **The field is young and unsettled.** Four serious tools (OpenSpec, Spec Kit, Kiro, Tessl) disagree on fundamentals — even on *which artifact is the source of truth*. There is no consensus to copy.
- **Our repo already took a contrarian position.** `NORTH-STAR.md` line 13: *"CODE — the source of truth."* Most of the field says the *spec* is truth. We should understand that fork deliberately, not by accident.
- **Goal of the opening:** shared vocabulary + a map. By the end you can place any tool — and our harness — on one diagram.

> No conclusions yet. Just the lay of the land.

---

## The core problem: intent that won't stay put

AI writes code **fast**. The bottleneck moved from *typing code* to *keeping code and intent aligned* as both change.

- **Drift is the default.** You spec a behaviour, the agent implements it, then three changes later the code does something the spec never mentions — or the spec promises something the code dropped. Now neither is trustworthy.
- **Two failure modes, equally bad:**
  - *Stale spec* — doc says X, code does Y. The "source of truth" lies.
  - *Phantom spec* — spec describes a feature that was never built (or silently stubbed).
- **The real question is durability:** when intent and implementation conflict, **which one wins, and how is that enforced — mechanically, not by good intentions?**

*Source: `NORTH-STAR.md` ("Anti-goals"): "Docs that cite files which don't exist.")*

---

## Key terms

| Term | Working definition |
|---|---|
| **Spec** | A human-readable statement of *what* the system should do (behaviour, interfaces, acceptance). Markdown, usually. |
| **Code** | The executable, tested artifact. The *what* made real. |
| **Harness** | The tooling around the agent that drives the build loop and enforces the rules — *not* the app it produces. |
| **SDD** | Spec-Driven Development: making a spec the explicit unit of work the agent operates on. |
| **Drift** | Spec and code disagree. The condition SDD exists to fight. |
| **Reconciliation** | The mechanism that re-aligns spec ↔ code, and decides who wins on conflict. |
| **EARS** | *Easy Approach to Requirements Syntax* — constrained templates ("WHEN \<trigger\>, the system SHALL \<response\>") for unambiguous requirements. Used by AWS Kiro's `requirements.md`. |

---

## A map of the field

Two independent axes. Every tool — and ours — is a point in this grid.

**Axis 1 — Direction of truth (who wins on conflict):**

| Position | Meaning | Who |
|---|---|---|
| **Spec-first** | Spec is canonical; code is generated/regenerated from it | Tessl, Spec Kit, Kiro, OpenSpec |
| **Code-first** | Code is canonical; spec is *projected from* the code | **Us** (`NORTH-STAR.md`) |
| **Reconciliation-based** | Neither is fixed; a sync step merges/audits both ways | OpenSpec archive, Spec Kit `/analyze` |

**Axis 2 — What plays the role of "spec":**

- **doc-as-spec** — prose/Markdown requirements (Spec Kit, Kiro, OpenSpec, our `spec/`)
- **test-as-spec** — executable acceptance checks are the binding contract (our `proof-gate`; classic TDD)
- **types-as-spec** — schemas/types/contracts constrain the code (dependently-typed & contract-driven lineage)

> The interesting tools mix these. Our harness is **code-first + doc-as-spec for reading + test-as-spec for proof.**

---

## What we'll cover

1. **The problem & the field** *(you are here)* — drift, vocabulary, the truth-direction axis.
2. **The four competitors, deeply** — OpenSpec's delta-spec tree · Spec Kit's Constitution→Implement pipeline · Kiro's three-file EARS gates · Tessl's spec-as-projection.
3. **Academic rigor** — formal specs, refinement, EARS, what "verified" actually means.
4. **Our six design bricks:**
   - repo skeleton (`harness` / `spec` / code / `.claude` contract)
   - spec format · reconciliation (who wins) · the build loop · the `.claude` adapter · validation by simulating the workflow
5. **Decisions** — where we agree with the field, where we deliberately don't, open forks.

*Our current shape (real folders): `NORTH-STAR.md`, `.claude/commands/{new,change,sync}.md`, `.claude/agents/{spec-projector,reviewer}.md`, `.claude/skills/{proof-gate,agentic-patterns}/`.*

---

# OpenSpec
### Agent-agnostic spec-driven development, built on a living spec tree

---

## What it is + who's behind it

- **OpenSpec** by **Fission-AI** — a lightweight, **agent-agnostic** spec-driven development (SDD) tool for AI coding assistants. MIT, **~55.7k GitHub stars**, active through mid-June 2026.
- Core idea: agree on **WHAT** before code. Split the repo into a **source-of-truth spec tree** and a **proposed-changes tree**; a sync/archive step merges change deltas back so the spec **grows as changes land**.
- Pure markdown + a CLI + generated instruction files (`CLAUDE.md`/`AGENTS.md` + per-tool slash commands). **No IDE lock-in** (vs Kiro), **no Python** (vs Spec Kit).
- Strong dogfooding: the tool specs **itself** with **~48 capability folders**.

```
openspec/                  # created by `openspec init`
  config.yaml              # active schema/profile
  specs/                   # SOURCE OF TRUTH — behavior NOW
    <capability>/spec.md   # one capability per folder (cli-validate/, schema-resolution/)
  changes/                 # PROPOSED modifications (live until archived)
    <change-name>/         # verb-led kebab-case (add-global-install-scope/)
      proposal.md  design.md  tasks.md
      specs/<capability>/spec.md   # DELTA spec for this change
    archive/YYYY-MM-DD-<change-name>/
  initiatives/  explorations/      # durable + exploratory planning
```
*Source: github.com/Fission-AI/OpenSpec (repo metadata + contents listings)*

---

## Spec format — requirements + scenarios

Markdown, **RFC-2119 SHALL prose + WHEN/THEN/AND bullets** (NOT EARS — the word appears nowhere in conventions/concepts). A capability `spec.md`:

```markdown
## Purpose
<capability description>

## Requirements
### Requirement: Install Scope Selection
The init command SHALL support install scope selection.   # narrative + 1 normative SHALL

#### Scenario: User picks global scope
- **WHEN** the user selects global install
- **THEN** commands are written to the user home directory
- **AND** the project config records the scope
```

- **Hard rule** (verified): every requirement MUST have descriptive text AND **≥1 `#### Scenario:`**.
- **Singular focus** — one responsibility per capability folder.
- **Delta specs** (inside a change) use operation headers — and the spec.md *template itself* is a delta:

| Header | Merge effect |
|---|---|
| `## ADDED Requirements` | add requirement |
| `## MODIFIED Requirements` | replace existing requirement |
| `## REMOVED Requirements` | remove it |
| RENAMED (FROM/TO) | rename |

*Rationale (concepts doc): "A delta shows exactly what's changing. Reading a full spec, you'd have to diff it mentally against the current version."*

---

## Spec <-> code reconciliation & drift

Two distinct mechanisms — **don't conflate them**:

| Layer | What it does | Determinism |
|---|---|---|
| **spec<->spec** `/opsx:sync`, `openspec archive` | Merge change deltas into `specs/` (ADDED/MODIFIED/REMOVED/RENAMED). **Idempotent**, no dup requirements. | Mechanical-ish, AI-driven |
| **spec<->code** `/opsx:verify` (expanded, **opt-in**) | LLM reads tasks.md + deltas, searches code, reports drift. | **Non-deterministic** |
| **structure** `openspec validate --strict --json` | Structure only: required sections, every-req-has-scenario, "No deltas found". CI gate. | Fully mechanical |

- `/opsx:verify` 3 axes: **Completeness** (counts `- [x]` vs `- [ ]`, "Tasks: X/N complete") · **Correctness** (matches spec) · **Coherence** (follows design). Output: CRITICAL / WARNING / SUGGESTION with file:line.
- **Key gap:** `validate` checks structure, **not truth** — it does NOT confirm a MODIFIED req matches an existing one, and **never touches code**. There is **no `openspec sync` or `openspec diff` CLI verb**; sync is a skill.
- **Conflict handling** when multiple changes touch one spec is **UNSPECIFIED** — no documented 3-way merge.

*Source: specs-sync-skill, opsx-verify-skill, cli-validate spec.md*

---

## Workflow — commands, not stages

Install `@fission-ai/openspec` (Node 20.19.0+) -> `openspec init` (pick tools + profile) -> `openspec update` refreshes agent instructions.

**The loop:**
1. **PROPOSE** — `/opsx:propose <idea>` scaffolds the change folder: proposal -> deltas -> design -> tasks, in dependency order.
2. **REVIEW** — human refines artifacts *before code*; `openspec validate --strict`; `view`/`list`/`show`/`status`.
3. **APPLY** — `/opsx:apply` implements tasks.md, ticking checkboxes.
4. **VERIFY** (expanded, optional) — `/opsx:verify` AI-checks code vs spec.
5. **SYNC/ARCHIVE** — `/opsx:sync` merges deltas; `/opsx:archive` validates + dates the folder into `changes/archive/`.

- **CORE profile:** `propose · explore · apply · sync · archive`. **EXPANDED adds:** `new · continue · ff · verify · bulk-archive · onboard`.
- Workflow is **data, not prompt**: per-schema `schema.yaml` artifact graph — proposal -> specs+design -> tasks (requires BOTH) -> apply. Forkable via `openspec schema fork`; a second `workspace-planning` schema already exists.

*Philosophy (workflows doc): "Commands are things you can do, not stages you're stuck in" · "Dependencies are enablers—they show what's possible, not what's required next."*

---

## Strengths / weaknesses — and for OUR harness

**Strengths**
- Clean **two-zone** model: current truth vs proposed change, explicit on disk.
- **Delta requirements** -> small, intent-shaped, reviewable diffs.
- Sync/archive = **living spec** via verified idempotent merge.
- Genuinely **agent-agnostic**; deterministic **structural** gate (`validate --strict --json`).

**Weaknesses**
- Spec<->code reconciliation is **only semantic/LLM** and **opt-in** — a green run never fails a wrong impl.
- Verify is **non-deterministic**; can hallucinate "implemented" or miss gaps.
- **No runtime/behavioral proof** — correctness asserted by *reading* code, never executing it.
- Multi-change conflict merge **unspecified**; peripheral surface (initiatives/explorations/workspaces) risks **ceremony creep**.

| STEAL | AVOID |
|---|---|
| Two-zone disk model + explicit merge-on-completion as the spine | Letting reconciliation rest on an LLM *reading* code — boot the app, run real behavior |
| Delta ADDED/MODIFIED/REMOVED/RENAMED as the unit of change | Treating `validate` pass as "reconciled" — keep structure-gate and proof-gate distinct |
| Hard rule: every req has text + ≥1 scenario, enforced in a **git hook** | 4-artifact ceremony per tiny change — make heavy artifacts opt-in |
| Schema-as-data dependency graph (declarative, forkable) | Relying on generated AGENTS.md reminders as the sync mechanism — enforce mechanically |
| verify's 3-axis framing (completeness/correctness/coherence) — **but back it with EXECUTION** | Claiming EARS when it's SHALL prose — be honest or commit to a checkable grammar |

*Source: OpenSpec concepts/workflows/cli docs; verified repo corpus*

---

# GitHub Spec Kit
### Constitution → Specify → Clarify → Plan → Tasks → Implement
*Agent-agnostic spec-driven toolkit — intent as source of truth, code generated from it*

---

## What it is + layout

- **Agent-agnostic toolkit**: one set of templates/scripts drives 30+ AI coding agents (Copilot, Claude Code, Gemini, Codex, Cursor, Windsurf, Zed, Kiro). Knowledge lives in `templates/` + `scripts/`, not a frozen app — "no lock-in."
- Pipeline runs as slash commands, all carrying the **`/speckit.`** prefix; each maps to an agent-skill id (e.g. `speckit-clarify`).
- `specify init <name> --integration <agent>` (or `init .` / `--here`, `--force` to overwrite) scaffolds two roots. Requires **uv + Python 3.11+**; CLI via `uv tool install` or `uvx`.

```
.specify/                      # the toolkit's brain (agent-agnostic)
  memory/constitution.md       # project-wide MUST principles, read by every phase
  templates/                   # spec/plan/tasks/checklist/constitution templates
    overrides/                 # highest-priority template layer (project-local)
  scripts/bash/                # create-new-feature.sh, setup-plan.sh, ... (+ powershell/)
specs/                         # per-feature, human-readable
  001-<feature-slug>/          # auto-numbered by create-new-feature.sh
    spec.md plan.md tasks.md research.md data-model.md quickstart.md
    contracts/                 # api-spec.json, ...
.claude/commands/              # per-agent command files installed at init
```

- **Template resolution (first match wins, used entirely):** overrides > installed presets (by `priority`) > extensions (by `priority`) > Spec Kit core. The feature directory is the unit: **one feature = one numbered folder.**

*Source: github/spec-kit README; docs/reference/presets.md*

---

## Spec format

- **Markdown, abstraction-enforced**: the spec phase *forbids* implementation detail — tech stack lives in `plan.md`; success criteria must be "technology-agnostic and measurable" (vague adjectives like *fast/scalable/secure* get flagged).
- Authored by the agent from a natural-language prompt, refined via dialogue. Three sections are **mandatory**: User Scenarios & Testing, Requirements, Success Criteria.

```
# spec-template.md (order)
User Scenarios & Testing
  User Story 1 - <Title> (Priority: P1)   # Why this priority / Independent Test / Acceptance Scenarios
Edge Cases
Requirements -> Functional Requirements + Key Entities
Success Criteria -> Measurable Outcomes
Assumptions
Review & Acceptance Checklist
```

- **Granularity:** feature-level, split into independently-testable, priority-ranked **P1/P2/P3** user stories — each a standalone, deployable MVP slice.
- **Notation:** acceptance = **Given/When/Then** (not EARS). Ambiguity surfaced inline:
  `System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]`
- Philosophy: templates act as **sophisticated prompts** that constrain LLM output toward quality. Phases map to requirements (`spec.md`) / design (`plan.md` + `research.md` + `data-model.md` + `contracts/`) / tasks (`tasks.md`).

*Source: templates/spec-template.md; spec-driven.md*

---

## Reconciliation — the weakest, least-enforced part

> No automated spec↔code drift **gate**, no CI check, no hook. The official docs site doesn't even cover ongoing sync. Three opt-in layers:

| Command | Reads code? | Writes | Detects |
|---|---|---|---|
| `/speckit.analyze` | **No** (artifact-only) | None — "Do not modify any files" | dup, ambiguity, underspec, constitution, coverage gaps, inconsistency |
| `/speckit.converge` | **Yes** | **Append-only** `## Phase N: Convergence` to `tasks.md` | missing / partial / **contradicts** / **unrequested** |
| evolving-specs guide | manual | manual | n/a (3 competing models) |

- **`/analyze`**: 6 sequential passes, a **requirements→tasks coverage matrix**, orphaned-task + terminology-drift detection, 4 severity tiers (CRITICAL/HIGH/MEDIUM/LOW; constitution MUST-violations = CRITICAL), findings capped at 50. Audits `spec↔plan↔tasks↔constitution` only — **never the code**.
- **`/converge`** *does* read the codebase (builds a code-scope map from file paths in plan/tasks) and flags drift (`contradicts`) and code-ahead-of-spec (`unrequested`) — but its **only write is appending tasks**: an `unrequested` finding becomes a "review/justify or remove" task, never a deletion or a spec rewrite.
- **Evolving-specs** offers 3 manual models with no enforced default: **Flow-Forward** (new numbered dir per iteration, historical record), **Living Spec** (spec is the contract → regenerate downstream → re-run analyze), **Flow-Back** (let implementation reshape artifacts).
- **Bottom line:** spec is doctrinally the source of truth, drift *is* detected, but everything is opt-in commands a human must remember to run; the only code-vs-spec write is appending a to-do.

*Source: templates/commands/analyze.md, converge.md; docs/guides/evolving-specs.md*

---

## Workflow + steal / avoid

**End-to-end (all `/speckit.*` slash commands):**
1. `specify init <name> --integration <agent>` — scaffold `.specify/` + agent commands (non-interactive default: Copilot)
2. `/speckit.constitution` — author/refresh `.specify/memory/constitution.md`
3. `/speckit.specify "<what/why>"` → makes `specs/00N-slug/spec.md` (no tech)
4. `/speckit.clarify` (recommended) — resolve `[NEEDS CLARIFICATION]` pre-plan
5. `/speckit.plan "<tech>"` → `plan.md` (+ research/data-model/contracts/quickstart)
6. `/speckit.tasks` → `tasks.md`, `[P]` parallel markers, dependency order
7. `/speckit.analyze` (optional gate) · `/speckit.checklist` (optional)
8. `/speckit.implement` — parse tasks, run in dependency order · `/speckit.taskstoissues` (optional)
9. `/speckit.converge` (maintenance) — append a Convergence phase

*Also: a YAML workflow engine (command/prompt/shell/gate/if/switch/while/fan-out…) chains steps with human checkpoints; state persists for resume.*

| Steal | Avoid |
|---|---|
| `/analyze`'s deterministic, rerunnable 6-pass audit + coverage matrix + 4 severity tiers — **but extend to compare spec vs real CODE** | The reconciliation gap: artifact-only `/analyze` + append-only `/converge`, no CI/hook — make drift a **mechanical gate that can fail** |
| `constitution.md` as a persistent home for non-negotiable MUST rules | Append-only convergence as the answer to drift — actually **re-project the spec from code** |
| `converge`'s 4-way gap vocab: **missing / partial / contradicts / unrequested** | 3 competing evolving-spec models with no default — pick one ritual |
| `[NEEDS CLARIFICATION:]` markers + a dedicated `/clarify` phase | Treating Given/When/Then prose as "testing" — `/implement` has no boot-and-verify gate |
| P1/P2/P3 independently-testable MVP slices; abstraction enforcement (tech out of spec) | Heavy Python/uv + bash/PowerShell toolchain if work can live in-agent; `init --here --force` clobbering `constitution.md` |

*Source: github/spec-kit README; docs/reference/workflows.md*

---

# AWS Kiro
### The spec-driven agentic IDE — `.kiro/specs/<feature>/` as the unit of work

*An AWS agentic IDE on Code OSS (+ a Kiro CLI) where a three-file spec drives the build, gated by phase approvals.*

---

## What it is + the layout

- **AWS agentic IDE** built on Code OSS / VS Code; also ships a **Kiro CLI** that speaks the open Agent Client Protocol (ACP).
- **Unit of work = a spec folder**, not a chat. Each feature gets a committed `.kiro/specs/<feature>/` directory; project context lives in `.kiro/steering/`.
- Everything is **plain markdown, committed to git**, so it travels with the repo.

```
.kiro/
  steering/                 # persistent context, injected into interactions
    product.md              # purpose, users, key features, objectives
    tech.md                 # frameworks, libraries, constraints
    structure.md            # file org, naming, import & arch patterns
    api-standards.md        # custom steering (e.g. testing-standards.md)
  specs/
    <feature-name>/
      requirements.md       # user stories + EARS criteria (or bugfix.md)
      design.md             # architecture, mermaid, interfaces, schemas
      tasks.md              # numbered, dependency-linked checklist
```

- Workspace scope `.kiro/` at repo root; global scope `~/.kiro/`.
- *Source: kiro.dev/docs/steering, /docs/getting-started/first-project (".kiro folder containing specs and steering files")*

---

## The spec format: requirements → design → tasks (+ EARS)

Three artifacts, each a distinct **approval-gated phase**:

| File | Content | Grammar |
|------|---------|---------|
| `requirements.md` | User stories `As a <role>, I want <x>, so that <y>` + acceptance criteria | **EARS** |
| `design.md` | Architecture, mermaid/sequence diagrams, component interfaces, data models, API endpoints, error handling | — |
| `tasks.md` | Numbered, dependency-linked checklist; each task links to related requirements | checkbox markers |

**EARS** (Easy Approach to Requirements Syntax) — Kiro documents the primary template prominently:

```
WHEN <condition/event> THE SYSTEM SHALL <expected behavior>
```

- Fuller EARS standard (Ubiquitous SHALL · Event WHEN · State WHILE · Optional WHERE · Unwanted IF…THEN) is **EARS-standard context**, not enumerated in Kiro's own docs.
- Task markers: `- [ ]` not started · `- [-]` in progress · `- [x]` complete. Bugfixes use `bugfix.md` (current vs. expected behavior) instead of user stories.
- *Source: kiro.dev/docs/specs, /docs/specs/feature-specs, /blog/introducing-kiro*

---

## Reconciliation: first-class, but advisory

Spec and code are kept in sync **on demand**, framed as "living documentation" — there is **no continuous drift detector and no CI gate**.

- **Sync Files** (in `tasks.md`): Kiro "automatically marks completed tasks" against the code.
- **Conversational reconcile**: ask "Check which tasks are already complete" → Kiro analyzes the codebase and identifies implemented functionality.
- **Iterative refinement**: update requirements → refine design → re-sync to "create new tasks that map to the new requirements". Design-First and code-first variants derive artifacts from existing design/code.
- **Analyze Requirements**: authoring-time check surfacing "logical inconsistencies, ambiguities, conflicting constraints, and gaps" before design.

> Net: bidirectional and human-triggered — a strong primitive, but **advisory only**. Specs can silently rot if no one clicks Sync. *(Steering-as-code-review governance is NOT stated by Kiro's current docs.)*

- *Source: kiro.dev/docs/specs/best-practices*

---

## Workflow + steal / avoid

**End-to-end:** open project (IDE or `kiro-cli acp`) → **Generate Steering Docs** → create spec from plain-English prompt ("Add a user authentication system with login, logout, password reset") → pick a variant:

- **Requirements-First** (default) · **Design-First** · **Quick Plan** (all phases, **no approval gates**).

Then **Requirements → Design → Tasks** (each review + approve) → **Execute**: Kiro builds a dependency graph and runs in **waves** ("Waves execute sequentially; tasks within a wave execute concurrently"). **Agent Hooks** automate side effects (save → update tests; pre-commit → scan creds); **MCP** adds tools.

| Steal | Avoid |
|-------|-------|
| 3-phase artifact split as separate committed files per feature | Treating `[x]` as proof of correctness — pair every task with an executable proof gate |
| EARS as a testable acceptance grammar | Manual/advisory reconcile — detect drift continuously and **fail closed** |
| Approval gates + a graduated bypass (not all-or-nothing) | Coupling spec workflow to one IDE's buttons; keep it tool-neutral (ACP is the right move) |
| Design phase reads the **real codebase** before designing | Brittle in-band status markers gating execution (bug #8859: agent reads `[-]` and refuses to run) |
| Steering files with scoped injection (always / fileMatch glob / manual / auto) | Conventional-only traceability — enforce every requirement maps to a task **and a test** |

- *Source: kiro.dev/docs/specs, /docs/cli/acp, github.com/kirodotdev/Kiro/issues/8859*

---

# Tessl & the Emerging SDD Landscape

A field guide for design decisions: what to steal, what to avoid

---

## Tessl — what it is, and which generation you're copying

Tessl makes the **spec the durable source-of-truth** and treats code/tests as regenerable projections. There are **two distinct generations** — confusing them is the #1 design error.

| | Gen 1 — "Tessl Framework" (beta) | Gen 2 — current, shipping |
|---|---|---|
| Model | Spec-as-source **code generator** | **Agent-enablement platform**: package manager + eval tools for reusable agent context (Skills/Rules/Plugins) |
| SDD delivery | Built into the framework | Installable plugin: `tessl-labs/spec-driven-development` (formerly a "tile") |
| Spec↔code | **1:1** `.spec.md` → one generated file, marked `// GENERATED FROM SPEC - DO NOT EDIT` | Spec governs code via `targets:` globs; humans edit code, then reconcile |
| What's reviewed publicly | Böckeler's Fowler-site review | The methodology plugin (generation engine stays closed) |

- Gen 2 is **agent-agnostic**: ships a Tessl MCP server + Skills/Rules that plug into Claude Code, Cursor, etc.
- A **tile→plugin migration is in progress** (`tile.json` → `.tessl-plugin/plugin.json`); both coexist, so 3rd-party write-ups describe different systems.

*Source: martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (Böckeler, 2025-10-15); docs.tessl.io/introduction-to-tessl/how-tessl-works*

---

## Tessl — on-disk layout (Gen 2)

`tessl init [--agent <name>]` configures the host agent and writes a manifest.

```
tessl.json              # {name:"workspace/project", mode:"managed"|"vendored",
                        #  dependencies:{"workspace/plugin":"version"}}
.tessl/
  .gitignore            # auto-managed by mode
  RULES.md              # GENERATED, consolidated plugin rules — never committed
  plugins/<workspace>/<plugin>/
    .tessl-plugin/plugin.json
    skills/  rules/
CLAUDE.md               # context file w/ Tessl MCP instructions
AGENTS.md               # if present, Tessl appends ref to .tessl/RULES.md (<!-- tessl-managed -->)
.mcp.json               # Tessl-managed MCP config (Claude Code)
specs/                  # *.spec.md files (verification skill globs specs/ -name "*.spec.md")
```

- **`managed`** = plugin contents gitignored like `node_modules` (run `tessl install` after clone). **`vendored`** = committed.
- The SDD plugin repo (`github.com/tesslio/spec-driven-development-tile`, active, ~41★, **not archived**) ships: **4 skills** (requirement-gathering, spec-writer, spec-verification, work-review), **3 rules** (spec-before-code, one-question-at-a-time, spec-format-compliance), `docs/` (spec-format.md, spec-styleguide.md), `scripts/` (validate-specs.sh, check-spec-links.sh), `evals/` (9 scenarios).

*Source: docs.tessl.io/reference/configuration; github.com/tesslio/spec-driven-development-tile*

---

## Tessl — spec format & the [@test] mechanic

Specs are Markdown, `.spec.md` extension, **YAML frontmatter**. `targets:` is **required** (≥1 path or glob — the code the spec governs).

```markdown
---
name: Database Architecture
description: Key design patterns used across our data models
targets:
  - ../src/models/**/*.py
---
## Soft deletes
Records are never hard-deleted; `deleted_at` is stamped...
[@test] ../tests/models/test_soft_delete.py
```

- **Inline test linking** is the defining move: `[@test]` sits **next to the requirement it verifies** → mechanical spec↔test traceability.
- Body = context-rich prose under one heading per feature area (behaviors, edge cases, errors, optional API-contract block).
- **No EARS notation. No Kiro-style requirements/design/tasks split** — Böckeler notes Tessl works "at quite low abstraction level, per code file."
- Caveat on the famous line: *"specs don't need a specific format"* is **marketing-blog framing** (Debois), not the plugin docs — `spec-format.md`/`spec-styleguide.md` actually **prescribe** conventions.

*Source: spec-format.md + spec-writer/SKILL.md (tesslio/spec-driven-development-tile); Debois blog "10 things you need to know about specs", 2025-10-29*

---

## Tessl — reconciliation: the headline differentiator

The **spec-verification skill** is the most stealable part — a runnable, 6-step drift loop:

1. **Find all specs** — `find specs/ -name "*.spec.md"`
2. **Validate structural integrity** — every `targets:` resolves, every `[@test]` points to a real test (`validate-specs.sh`, `check-spec-links.sh`)
3. **Run linked tests** — execute referenced files, diagnose failures
4. **Spot-check targets for drift** — read code vs documented behavior
5. **Check drift signals** — behavior changed but spec didn't · orphan test, no requirement · requirement, no test · renamed/deleted file still referenced · undocumented code path
6. **Fix drift** — emit a structured report

The "spec-as-source registry" idea: Gen-1 launched a **Spec/Usage Registry** (Sept 2025, "10,000+ pre-built specs") of version-accurate library APIs to kill API hallucination; Gen-2 registry "evaluated 2,000+ public skills against best practices."

> **Two honest caveats.** Regeneration is **non-deterministic** (Böckeler: same spec → different code across runs) — it's iterative, not a round-trip. And step 6 **defaults to editing the SPEC to match code** — an agent can quietly rewrite intent to match a *buggy* implementation unless a human gates it.

*Source: spec-verification/SKILL.md; Böckeler (Fowler site); tessl.io/blog launch, 2025-09-23*

---

## Tessl — steal vs. avoid

| Steal | Avoid |
|---|---|
| The spec-verification **drift loop as a mechanical gate** (resolve globs → assert links → **run tests** → spot-check → report) | Promising **deterministic** "regenerate code from spec" — their own review shows non-determinism |
| **Inline `[@test]`** per requirement → checkable, not aspirational, traceability | Rigid **1:1 spec-per-file** granularity (Böckeler: risks "inflexibility AND non-determinism" of MDD+LLMs) |
| **`targets:` globs** binding a spec to the exact code it governs → scoped per-spec checks | Auto-"fix drift" by **defaulting to rewrite-the-spec** — require a human call on who's authoritative |
| Ship gates as **plain shell scripts** in-repo (agent-agnostic, runs in any CI) | Importing the **SaaS surface** (registry accounts, workspaces, orgs, login/api-keys, eval projects) |
| Keep a **code→spec recovery** step (Gen-1 `@describe`) — re-project spec from reality, not just forward | `GENERATED … DO NOT EDIT` **frozen-output** markers — expect edits, then reconcile |
| Lightweight Markdown+frontmatter; *"tests define intent too"* | Tying reconciliation to a **proprietary MCP / mid-churn packaging** (tile.json vs plugin.json) |

- **Workflow worth borrowing**: spec-before-code rule + **one-question-at-a-time** requirement gathering + a **single human approval gate** before implementation.
- **Don't drop why-level traceability entirely** just because Tessl does — some rationale layer helps when code and spec disagree.

---

## The rest of the SDD landscape

Where the field is converging — and each tool's single most notable idea.

---

## Emerging SDD tools — landscape

| Tool | Category | Single most notable idea |
|---|---|---|
| **BMAD-METHOD** | Agile-team-as-agents (OSS) | Up-front PM/Architect agents → **"shard"** PRD+arch into self-contained per-story files carrying full context to the dev agent (no planning→impl context loss) |
| **AGENTS.md** (Linux Fdn) | Tool-agnostic standard | "README for agents" with **nearest-file-wins precedence** down the tree; 60k+ repos, 20+ agents |
| **Cursor / Windsurf Rules** | IDE rules-as-config | `.cursor/rules/*.mdc` carry **globs + `alwaysApply` + agent-requested** metadata → composable, scoped context vs one monolithic prompt |
| **Conductor** (Google, Gemini CLI) | Context-driven dev | Specs/plans **persist as Markdown beside code**; engineer shifts from coder → orchestrator |
| **Conductor.build** | Parallel-agent macOS app | **Git-worktree isolation per agent** → concurrent agents never collide, reviewable merge |
| **Intent / Cosmos** (Augment) | Multi-agent spec workspace | One **living spec** drives Coordinator→Specialists→**Verifier**; checked vs spec before merge; Context Engine over 400k+ files |
| **Task Master** | Spec decomposition (MIT) | PRD → **dependency-aware task graph**; AI PM inside Cursor/Windsurf/Roo |
| **GSD** | Spec-driven framework | Differentiates on **execution/orchestration depth** of the specify-plan-execute-verify loop |
| **DSPy** (Stanford) | Program-not-prompt LLMs | The **signature as executable spec** (`question -> answer`); compiler/teleprompter auto-tunes prompts |
| **TDD-for-LLMs** | Research/benchmarks | **Tests as the executable truth** — supplied as both instruction and verifier (TiCoder, arXiv:2402.13521) |
| **PRPM** | Cross-tool registry | "**npm for AI coding tools**" — prompts/rules/skills/agents as installable, versioned deps |

- **Convergent core loop**: specify → plan → decompose → execute → verify. Differentiation is in *which stage* each tool deepens.
- **Three frontiers to watch**: (1) portable context standards (AGENTS.md, PRPM); (2) safe multi-agent parallelism (worktree isolation); (3) compiled/test-as-spec (DSPy, TDD-for-LLMs) where the spec is *executed*, not hand-written.

*Sources: github.com/bmad-code-org/bmad-method · agents.md · docs.cursor.com/context/rules · developers.googleblog.com (Conductor) · conductor.build · augmentcode.com/blog/intent · github.com/eyaltoledano/claude-task-master · github.com/stanfordnlp/dspy · arxiv.org/abs/2402.13521 · github.com/pr-pm/prpm*

---

# Academic Rigor
## What the literature demands of a spec-driven system — and how this harness answers it

*Requirements engineering · formal vs. lightweight specs · spec/code drift · "spec as source code" · verification & proof*

---

## The core inversion

- **Traditional spec:** a document humans read, then drift away from.
- **Spec-driven (SDD) spec:** an artifact that *executes* as a validation gate in CI — it fails the build when reality diverges.
- The contested question every team must answer **deliberately**:

| Camp | Source of truth | Code is… |
|------|-----------------|----------|
| **Radical** (Grove/OpenAI) | the spec | a regenerable byproduct |
| **Conservative** (Thoughtworks) | the spec as *behavioral contract* | the maintained, runnable artifact |

- Thoughtworks rates SDD **"Assess"** (promising, unproven) and names the antipattern: *heavy upfront specs + big-bang releases* = waterfall in disguise.

*Source: arXiv 2602.00180 "From Code to Contract"; thoughtworks.com/radar/techniques/spec-driven-development*

---

## Requirements engineering: EARS

Unconstrained natural language is the dominant source of ambiguity, vagueness, and incompleteness. **EARS** (Alistair Mavin et al., Rolls-Royce, IEEE RE'09) constrains prose into a fixed clause order and a tiny keyword vocabulary.

Grammar: `WHILE <precondition(s)>, WHEN <trigger>, the <system> SHALL <response(s)>`
> 0+ preconditions · 0–1 trigger · exactly one system name · 1+ responses

| Template | Pattern |
|----------|---------|
| Ubiquitous | `The <system> shall <response>` |
| State-driven | `WHILE <state>, the <system> shall <response>` |
| Event-driven | `WHEN <trigger>, the <system> shall <response>` |
| Optional-feature | `WHERE <feature>, the <system> shall <response>` |
| Unwanted-behaviour | `IF <trigger>, THEN the <system> shall <response>` |

*Source: alistairmavin.com/ears/*

---

## EARS in practice (and why it matters here)

Each EARS line names **one condition + one testable response** → it maps almost 1:1 to an acceptance test. That is exactly what makes drift *mechanically detectable*.

Our `examples/calc-agent/spec/calc-agent.md` is already EARS-shaped prose — rewritten to template:

```
Event-driven:    WHEN a function_call part is present, the agent shall
                 call calculator(**fc.args) and append the result.
Unwanted:        IF the tool raises, THEN the agent shall feed back
                 "error: {e}" rather than propagate the exception.
Unwanted:        IF max_steps is reached with no text answer, THEN the
                 agent shall return "(ran out of steps)".
Ubiquitous:      The calculator shall reject any AST node outside
                 {const, +,-,*,/,**,%, unary} with ValueError.
```

Each line is asserted by a keyless test — the spec becomes the test oracle.

---

## Formal vs. lightweight: a deliberate spectrum

| Approach | Cost | What it buys | Where to use |
|----------|------|--------------|--------------|
| Prose / PRD | low | readability | never the sole contract |
| **EARS / Spec-by-Example** | low | testable clauses | every behavioral req |
| **Types / contracts / properties** | medium | machine-checkable, self-syncing | most of the system |
| **TLA+ / formal** | high | bugs *no test or review finds* | the hard core only |

- **AWS** has run TLA+ in production since 2011 (DynamoDB, S3): formal methods find subtle design bugs and let engineers "verify deep changes are safe — or learn they are unsafe — without doing harm."
- Scope it to **concurrency, distributed protocols, agent control loops, irreversible ops**. Over-formalizing everywhere re-creates waterfall.

*Source: cacm.acm.org/research/how-amazon-web-services-uses-formal-methods/*

---

## Tests, types, properties AS the spec

> "Unit tests enumerate a handful of examples; a property/contract states the rule itself." — Hillel Wayne

- **Preconditions** (must hold on entry) · **postconditions** (guaranteed on exit) · **invariants** (always hold).
- Property-based testing explores hundreds of inputs while contracts assert correctness across deep call chains → **integration coverage "for free."**
- When code diverges, the property *fails* — the spec cannot silently lie.

Our calc-agent spec already states a true **safety invariant**, not examples:

```
Safety property: only {const, binary +-*/**%, unary +/-} are evaluated.
Any other node — names, calls, attribute access — raises ValueError
BEFORE evaluation; eval/exec are never used.
So  x + 1  and  __import__('os').system('echo hi')  are rejected.
```

*Source: hillelwayne.com/pbt-contracts/*

---

## Spec/code drift & reconciliation

Drift — code behavior diverging from its documented contract — is *"inherently difficult to avoid"* and **compounds silently** under periodic review. The research consensus: a **commit-time gate**, not a quarterly audit.

The four-part reconciliation discipline:
1. Any behavior change updates **both** spec and code in the **same** change (sync-owner-gate).
2. Make the spec **executable** so divergence trips a test immediately (EARS / examples / contracts).
3. For structural contracts, run **automated spec-vs-code comparison** (OpenAPI/route/model diff).
4. On detection, **force resolution before merge** — fail CI, auto-open a PR, or notify.

Drift-resistant *by construction*: literate programming (one source) and tests-as-spec (the spec is the passing check).

*Source: github.com/ChrysKoum/SpecSync; wasowski "sync-owner-gate"*

---

## Verification & proof — mapping our gate to the literature

Academic verification asks: *does the system meet its spec, observed — not asserted?* Our **proof-gate** (`.claude/skills/proof-gate/SKILL.md`) is that discipline operationalized:

```
1. Boot it.        Start the app for real (not just import).
2. Run the change. Exercise the new behaviour end-to-end.
3. Judge the OUTCOME, not the status.  A 200 with a wrong answer is a FAIL.
4. Bind every acceptance criterion to a real check.
                   An unbound criterion is not done.
```

| Academic concept | Our mechanism |
|------------------|---------------|
| Spec as oracle | EARS-style acceptance check (`…returns answer containing 396`) |
| Soundness ("no false pass") | "Never report a pass you didn't run" |
| LLM-judged output | sample the judge, require a stable majority |
| Coverage of obligations | every criterion bound to a running test |

---

## Lineage: literate & intent programming

- **Knuth, literate programming (1984):** author the program as an *explanation of intent* interleaved with code, in human reasoning order. One source **tangles** → runnable code, **weaves** → docs.
- The original, durable answer to drift: intent and implementation are *the same file* — nothing separate to desync. The conceptual ancestor of "spec as source of truth."
- **Spec-by-Example / living documentation** (Fowler 2002; Adzic, 50+ projects): derive specs from concrete domain-language scenarios, automate them as acceptance tests → the spec **is** the passing suite.
- Fowler's caution: *tests are always incomplete* — supplement examples with types, contracts, and review.

*Source: literateprogramming.com/knuthweb.pdf; thoughtworks.medium.com spec-by-example*

---

## "Spec as source code" — the discourse & the voices

- **Sean Grove (OpenAI):** code is a *"lossy projection"* of intent; code is ~10–20% of value, the other 80–90% is structured communication & verification. Don't "version the binary and shred the source." OpenAI's **Model Spec** (markdown) trains models, generates tests, and was a *"trust anchor"* during the sycophancy incident.
- **Anthropic engineering:** for AI agents the **tool/spec description IS the execution context** — wording-level changes alone moved SWE-bench error rates; iterate the spec via *evaluation-driven development*.

| Voice | Stance |
|-------|--------|
| Grove / OpenAI | radical: spec is the fundamental unit |
| Thoughtworks | pragmatist: behavioral contract, beware over-formalization |
| Fowler / Adzic | spec lives as executable acceptance tests |
| Wayne; Lamport / AWS | contracts/properties/types & TLA+ for the hard core |
| Knuth | literate: a document that contains the program |

---

## What rigor says a good spec-driven system MUST do

1. **Phrase requirements in EARS** — one condition, one testable response per line → the proof-gate can assert each.
2. **Declare the authority** — state in the harness that the spec is the human-readable *behavioral contract* and code is the runnable output (resolve radical-vs-conservative explicitly).
3. **Gate both directions** — commit-time gate forward (spec+code together) **and** a `/sync` step that re-projects the spec from current code so it never rots.
4. **Make the spec executable** — tests, contracts, properties, types; prove behavior, don't enumerate examples.
5. **Reserve formal methods for the hard core** — agent control loops, irreversible ops; not everywhere.
6. **Iterate spec wording with evals** — for AI-built parts, the spec is context; measure error rates.
7. **Stay small & modular** — avoid the "curse of instructions"; keep each unit reviewable and diffable.

*This is precisely the proof-first, spec-in-sync loop our `/new` and `/change` workflows enforce.*

---

# Our Repo: History & the Decisions We've Made

A spec-driven harness that turns a one-line idea into a working agentic AI app — gated by mechanical **proof**, not by "code matches a doc."

---

## The bloat curve: "fine & fast" → "overkill"

We grew the harness three times. Each version "worked" by its own bar, but the cost-to-understand outran the value.

| Version | Size (md+py) | Verdict | Why |
|---|---|---|---|
| v1 (early) | ~3.7k lines | "fine & fast" | thin, legible, did the job |
| v2 (recipes redo) | ~5.7k lines | "slower but worked" | copyable recipes, more rigor |
| v3 (overnight autonomous rewrite) | ~7.8k lines | **"OVERKILL"** | the owner could not explain his own repo's core mechanisms |

- The failure mode isn't a bug — it's **unmanageable surface area**.
- A harness you can't reason about can't be safely changed.

*Source: line counts from our v1→v2→v3 history; v3 = HEAD commit `befd889`, PR #28.*

---

## What the old harness DID (and it's real)

The v3 baseline (`befd889`, "harness v3: proof-first spec-driven") is a Claude-Code-only, spec-driven harness. Its thesis: **the only spec-driven tool that compiles and proves it ran.**

- `/build "<idea>"` → one 4-question intake (API key + runtime model at Q4)
- Fans out to sub-agents: `spec-writer`, `tech-designer`, `planner`, `spec-reviewer`, `plan-reviewer`
- Drafts a 4-file spec + `reports/implementation-plan.md`, runs a 6-check inline pre-flight
- **One** human approval (scope + stack + plan via AskUserQuestion), then runs **unattended to a green gate**
- Code generated fresh on `feature/<slug>-<date>` from recipes in `harness/patterns/`
- `.claude/commands/`, `.claude/agents/`, `CLAUDE.md` generated from `harness/` by `harness/generate.py --check`

*Source: `git show befd889:harness/harness.md`.*

---

## The two-zone honesty model

The architecture rests on an explicit split — and deliberately does **not** claim "pure spec-as-source end to end" because the repo couldn't back that claim.

| Zone | Source of truth | Contents |
|---|---|---|
| **Tested CORE** (reused, version-pinned) | **CODE** | async FastAPI server, ReAct/LangGraph loop (`force_finalize`, max-iter sizing, AST action-safety), `ok()/api_error()` envelope, session-scoped resources, `/traces` dashboard, the gate harness, UI shell, SQLite |
| **Generated DOMAIN** | **SPEC** | capability nodes, tools, prompts, EARS evals, domain UI screens |

- `/build` **configures** the core, never regenerates it (like a framework dependency).
- Two-zone also governs **who you fix** on a red check: core rule → fix the recipe; domain rule → fix the spec.

*Source: `git show befd889:harness/harness.md`, `spec/constitution.md`.*

---

## The spec format: EARS + `[@eval]` binding

A 4-file input contract plus an inherited, versioned constitution (`Version 1.0.0`, ~30 MUST/SHOULD rules, each bound to a mechanical owner).

```
spec/product.md          # what it does, success criteria, out-of-scope
spec/capabilities/*.md   # one per capability — EARS criteria, P1/P2/P3
spec/agent.md            # on/off layer ledger; every ON layer traces to a capability
spec/tech-stack.md       # provider, runtime model, sqlite+aiosqlite, deploy target
spec/constitution.md     # inherited; rules A–F, each -> a gate line / hook / lint / test
```

Every acceptance line is EARS **and** carries an executable binding token:

```
WHILE a file is loaded ... SHALL retain the uploaded file context
across turns ... [@eval: tests/test_file_retention.py::test_file_retention]
```

- Priorities: exactly **one P1** (the live capability); P2/P3 are deterministic journey-complete **stubs**, never silent gaps.

*Source: `git show d6def4a:spec/capabilities/file-analysis.md`.*

---

## The mechanical gate: "done" = exit 0

`make gate` exits 0 is the **only** definition of done. Two tiers; PROD is a strict superset of DEMO. The DEMO gate is genuinely outcome-based — **a 200 with a wrong answer FAILS.**

| # | DEMO check | Verdict |
|---|---|---|
| 1 | `[@eval]` lint — every EARS line resolves to an AST-collectable case | exit code |
| 2 | `uv run pytest` — FakeModel loop (≥2 iter, tool spans, `force_finalize`) + judge test + Playwright | exit code |
| 3–4 | server boots `python -m agent`; `/health` = `{"ok":true}` | exit code |
| 5 | **two-turn** run on one session — any Q2 error fails even if Q1 was perfect | exit code |
| 6 | judge-stable outcome eval — `SAMPLES=5`, mean ≥ `THRESHOLD - MARGIN` | exit code |
| 7 | Playwright UI — post-JS DOM contains a **real expected value**, not just non-empty | exit code |
| 8 | `/traces` renders ≥1 run with that run's spans (grep `RUN_ID`) | exit code |

*Source: `git show befd889:harness/workflows/gates.md` (31.8KB).*

---

## What WORKED — the baseline bar we keep

The old harness drove **real apps to a green mechanical gate.** That is the bar.

- **Data-analysis agent** — `d6def4a`, branch `feature/data-analysis-2026-06-20`: commit msg *"gate exits 0 (all 8 checks pass)"*, **40 files / 4,045 insertions** (full `agent/` package, `sessions.py`, `guardrails.py`, tests, Playwright e2e, `uv.lock`).
- **Support-triage agent** — `c85e982`, branch `feature/support-triage-2026-06-20`: **47 files / 3,353 insertions** incl. a Next.js `ui/`; keyless gate verified (eval_lint exit 0, 14 passed + 1 key-gated skip).
- **EARS → `[@eval]` binding works end to end** — `test_file_retention` exists at line 12; enforced by an AST lint that runs twice so it can't slip through either entry point.
- Each constitution MUST maps to a concrete owner → the constitution is **enforced, not preached.**

*Source: `git show d6def4a --stat`; `git diff --stat befd889 c85e982`.*

---

## What FAILED — candid

- **Prose re-typed every build.** `gates.md` = 31.8KB, `build.md` = 25.7KB, `constitution.md` = 12.8KB. Recipe code (`config.py`, `runner.py`, `eval_lint.py`, `demo_gate.sh`) is duplicated across files — exactly what `build.md` itself warns "is how contracts silently drift."
- **Dangling cross-references.** `build.md`/`gates.md`/`constitution.md`/`drift-auditor.md` repeatedly cite `reports/archaeology/SPEC-RECONCILIATION.md`, `COMPETITIVE-RESEARCH.md`, `HARDENING-LOG`. `git ls-tree -r befd889` → **NONE tracked** (only `reports/sessions/.gitkeep`). Every "(§ F)", "(iter 7)" points at a file that doesn't exist.
- **Owner couldn't explain his own repo.** The v3 "tested core" was really ~3k lines of **prose recipes an AI re-typed into code each build** — no `agent/` package, zero runnable tests in-repo.
- **A long tail of false-green traps** patched reactively: `asyncio_mode='auto'` skipping async tests; substring `[@eval]` false-greening TODOs; non-empty UI assert passing a "no data loaded" answer.

*Source: `wc -c` per file; `git ls-tree -r --name-only befd889`.*

---

## This session's RESET: lean, agent-agnostic v4

We **rejected** the v3 delivery model (prose-recipes-as-core) and locked a new direction: a lean, human-manageable, coding-agent-**agnostic** harness.

```
harness/   # agent-agnostic details & logic (the brains, portable)
spec/      # generated from the user's prompt
code/      # generated from the user's prompt
.claude/   # ONLY thin INDEXES pointing into harness/
```

- **Primary constraint: `spec/` and `code/` must ALWAYS reconcile** — both co-generated from one prompt, kept symmetric.
- v3's reconciliation was **one-way** (`drift-auditor`, intent-authoritative, RECORD vs FLAG). We keep the discipline but make the constraint **symmetric**.
- Tight iterative + human-in-loop; Claude-Code-native now, portable later.

---

## Corrections we made mid-session

We got the v4 shape wrong twice before locking it — worth recording so we don't regress.

| First (wrong) | Corrected to |
|---|---|
| Deleted `harness/`, inlined details into `.claude/` | `harness/` holds agent-agnostic details; `.claude/` is a thin index |
| Framed it one-way: "code is truth, spec is a projection" | Constraint is **symmetric reconciliation** — neither side silently wins |
| Built a throwaway example app to demo it | No throwaway app; the harness is the deliverable |

- Hard-coupling to `.claude/` would have re-created the lock-in we were escaping.

---

## Ideas we SALVAGED + what's next

**Keep (proven value):**
1. **Proof-it-ran gate** — done = app booted over HTTP and gave the **right** answer; 200-with-wrong-answer fails.
2. **`[@eval]` test-binding** — every EARS criterion bound to a real AST-resolved test; unbound → build fails.
3. **Judge-stability** — multi-sampled LLM judge with margin so exit-0 is deterministic.
4. **Thin-slice v1** — one real capability + honest deterministic stubs.
5. EARS acceptance criteria · 6. non-coder `/traces` dashboard.

**Open bricks (after this deck):** repo skeleton/contract · spec format · reconciliation mechanism · the harness workflow · the `.claude` index layer · validation by **simulating** workflows + review.

---

# Closing — Where We Stand in the Field

*Six slides: the comparison matrix, where we align with rigor, where we deviate and why, the bricks ahead, what good looks like, and how we'll validate.*

---

## The comparison matrix — every cell grounded

| Dimension | **Us (v4 target)** | OpenSpec | Spec Kit | Kiro | Tessl | Academic-ideal |
|---|---|---|---|---|---|---|
| **Folder layout** | 3 siblings: `harness/` + `spec/` + `code/`; `.claude/` = thin index | two-zone `openspec/specs/` vs `openspec/changes/` (~48 folders) | `.specify/` + `specs/<feat>/` | `.kiro/specs/` + `.kiro/steering/` | spec files + frontmatter, versioned in git | clean separation of intent vs artifact |
| **Spec format** | EARS lines + `[@eval]` + `targets:` glob, 1 file/capability | Markdown deltas (ADDED/MODIFIED/REMOVED) | `spec.md`/`plan.md`/`tasks.md` | `requirements`/`design`/`tasks`.md | Markdown + YAML frontmatter, inline `[@test]` | EARS (Mavin, IEEE RE'09) — 1 line ↔ 1 test |
| **Reconciliation** | symmetric; **intent wins**, working-but-wrong code FLAGged | delta proposal → apply → archive | `/analyze` read-only audit | approval gates per phase | drift-fix biased **spec→code** | spec+code update in same commit (sync-owner-gate) |
| **Verification / proof** | **boot + 2-turn HTTP + judge-stable outcome eval; 200-with-wrong-answer FAILS** | LLM `/verify` (reads artifacts) | severity-tiered static audit | checkbox tasks | shell scripts resolve globs + run tests | specs execute as CI gates |
| **Agent-agnosticism** | logic in `harness/`; `.claude/` regenerable adapter | CLI, agent-neutral | multi-agent, neutral | Kiro IDE + AGENTS.md | appends to AGENTS.md | format-neutral |
| **Leanness** | ~289 lines core; "hold in your head" bar | ceremony-heavy (changes/+archive/) | 3 artifacts/feature | steering + 3 artifacts | low-ceremony | minimal-but-complete |

*Source: OpenSpec dossier (Fission-AI, 55.7k★, MIT); Spec Kit `/speckit.analyze` 6-pass audit; Kiro `.kiro/steering/`; Tessl spec-verification tile; EARS = Mavin/Rolls-Royce IEEE RE'09.*

---

## Where we ALIGN with rigor

- **EARS acceptance criteria** — the academic consensus for testable, drift-detectable requirements. We keep it verbatim; one EARS line maps ~1:1 to one test.
  *Source: Mavin et al., IEEE RE'09; Kiro also documents WHEN/SHALL.*
- **Spec↔code↔test binding is machine-checkable** — `[@eval: path::case]` resolves via **AST collection, not substring**. Same spirit as Tessl's inline `[@test]` and committed `validate-specs.sh`. Unbound criterion ⇒ build fails.
- **Reconciliation as the central job** — matches the academic sync-owner-gate (spec + code must move together) and OpenSpec's "what we have vs what we want" framing.
- **Constitution-style non-negotiables, each with a mechanical owner** — Spec Kit (`constitution.md`), Kiro (`steering/`), and our baseline all converge here. Every MUST → a gate line / hook / lint.
- **Execution-grounded validation** — the field is moving toward "specs execute as CI validation gates" (*arXiv: Spec-Driven Development: From Code to Contract*); our proof gate is exactly that.

---

## Where we DEVIATE — and why

| We deviate | The field's norm | Why we deviate |
|---|---|---|
| **Proof = run it and judge the answer** | OpenSpec `/verify`, Spec Kit `/analyze`, Kiro read code/artifacts | Reading code can't catch a confident wrong answer. A **200 with a wrong answer FAILS** — the property *no competitor ships*. Proven across DataChat, data-analysis (`d6def4a`, 40 files, gate exits 0), support-triage. |
| **Intent wins on conflict** | Tessl biases drift-fix **spec→code** | Letting reality silently overwrite intent certifies wrong behavior green — the exact failure we exist to prevent. Working-but-wrong code is FLAGged for a human, never auto-blessed. |
| **No separate `changes/` zone** | OpenSpec's two-zone tree (its single best idea) | Full `changes/`+`archive/`+`initiatives/` is the ceremony creep that made v3 unexplainable. **Git branch = proposed, main = truth** — for free. (We may keep one throwaway `changes/<slug>.md` delta.) |
| **1 Markdown file per capability** | Kiro/Spec Kit 3-artifact split | 3 artifacts/capability is the artifact sprawl both dossiers flag as rot. Keep it to one screen. |
| **Claude-Code-only now** | AGENTS.md (60k repos, 20+ agents) | Deliberately rejected re-adding AGENTS.md (PR #23); it can't express Claude Code's command/subagent/skill/hook primitives the loop relies on. Logic stays in `harness/` so an adapter is a *generation target later*, not a rewrite. |

The hard constraint behind every deviation: **human-manageability**. The owner could not explain v3 (7.8k lines); v4 is "lean, hold-in-your-head."

---

## The open bricks ahead

Six bricks remain after this deck (none built yet — current HEAD `fda90ac` is the 289-line lean core; `harness/` and top-level `spec/` are still the v4 *target*):

1. **Repo skeleton & contract** — `harness/` (rules + recipes + gate scripts) · `spec/` (1 .md/capability) · `code/` · thin `.claude/`. *Open:* keep a `changes/<slug>.md` delta, or is the git branch the only change record?
2. **Spec format** — EARS + `[@eval]` + `targets:` glob, kept lean. *Open:* one binding syntax, not two.
3. **Reconciliation mechanism** — layered: **mechanical commit gate** (fail-closed) → **drift-auditor** (semantic) → **intent-wins** authority. *Open:* commit-time vs `/change`-time enforcement; the WIP escape hatch; the "reality-wins, I confirm" path.
4. **The harness workflow** — correct the committed **one-way** loop ("code is truth") to **symmetric co-generation**; wire reconciliation in as step ~3.5. Keep only 2 subagents (`spec-projector`, `reviewer`).
5. **The `.claude` index layer** — thin stubs that load `harness/` docs on demand, with a `generate --check` anti-drift owner.
6. **Validation by simulation + review** — see next-but-one slide.

*Note: NORTH-STAR.md still reads "Code is truth; this document is its projection" — brick 4 must flip this to symmetric.*

---

## What good looks like — the synthesis

A v4 that is **lean, honest, and reconciled**:

```
repo/
├── harness/        # agent-agnostic: harness.md (rules+workflow index),
│                   #   recipes/, gate scripts. The ONE place to read.
├── spec/           # one EARS+[@eval]+targets: .md per capability
├── code/           # the generated app — the executable truth
└── .claude/        # THIN index: commands/agents/skills load harness/ on demand
```

- **Spec format**: EARS body (the salvaged crown jewel) + one `targets:` glob so the gate knows which code a spec governs.
- **Reconciliation**: deterministic commit gate is the floor (the gap *every* competitor lacks); LLM drift-auditor only on top; **intent wins**, never auto-bless.
- **Proof**: keep the baseline DEMO gate verbatim — boot + two-turn HTTP + judge-stable eval. It's the proven performance bar.
- **Leanness as a feature**: a 4-step loop with 2 subagents stays explainable. Resist OpenSpec's schema engine and BMAD's 5-agent fan-out until a *second* workflow profile actually exists.

> The discriminating test: can one person read the whole harness in 30 minutes and explain its core mechanism? v3 failed this. v4 must pass it.

---

## How we'll validate v4

Three layers, each doing only what it's good at:

| Layer | Mechanism | Role |
|---|---|---|
| **Per-app floor** | Proof-it-ran gate (boot + 2-turn HTTP + multi-sample judge-stable eval) | Non-negotiable. Wrong answer on a 200 = FAIL. Kept *verbatim* from baseline. |
| **Cheap pre-flight** | Read-only coverage audit: every EARS line bound, every `targets:` glob covered, no orphans; severity tiers | Deterministic, fast, runs before the expensive boot. *Doubles as brick 3's mechanical gate.* |
| **Harness self-test** | **Simulate the workflows**: drive `/new` and `/change` against 2–3 sample ideas in CI; assert each ends in a **reconciled spec+code that passes the proof gate**. Plus an adversarial `reviewer` subagent that fixes nothing. | Validates the *harness itself*, not just an app. |

- **Keep the baseline that provably worked** — encode its hard-won false-green fixes (asyncio_mode, AST-not-substring resolution, empty-data) as **harness regression assertions** so they can't silently return.
- **Bound the cost** — sample ideas run keyless with `FakeModel` for mechanics; one keyed run for the real outcome eval.

*Source: baseline proof gate (data-analysis `d6def4a`, support-triage keyless gate); Anthropic eval-driven development; Spec Kit `/analyze`; Tessl `evals/` (9 scenarios).*

---

# Sources & further reading

- https://github.com/Fission-AI/OpenSpec
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/concepts.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/cli.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/docs/workflows.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/schemas/spec-driven/schema.yaml
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/schemas/spec-driven/templates/spec.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/openspec/specs/cli-validate/spec.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/openspec/specs/specs-sync-skill/spec.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/openspec/specs/opsx-verify-skill/spec.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/openspec/specs/openspec-conventions/spec.md
- https://raw.githubusercontent.com/Fission-AI/OpenSpec/main/openspec/changes/add-global-install-scope/specs/cli-init/spec.md
- https://api.github.com/repos/Fission-AI/OpenSpec (verified metadata: 55,746 stars; created 2025-08-05; pushed 2026-06-13; default branch main; MIT; ~420 open issues; description 'Spec-driven development (SDD) for AI coding assistants.')
- https://api.github.com/repos/Fission-AI/OpenSpec/contents/openspec (verified: config.yaml + specs/ + changes/ + initiatives/ + explorations/)
- https://api.github.com/repos/Fission-AI/OpenSpec/contents/openspec/specs (verified ~48 capability folders)
- https://api.github.com/repos/Fission-AI/OpenSpec/contents/schemas (verified schemas: spec-driven, workspace-planning)
- https://github.com/github/spec-kit
- https://raw.githubusercontent.com/github/spec-kit/main/README.md
- https://github.com/github/spec-kit/blob/main/spec-driven.md
- https://github.github.io/spec-kit/
- https://github.com/github/spec-kit/blob/main/docs/guides/evolving-specs.md
- https://github.com/github/spec-kit/blob/main/docs/reference/workflows.md
- https://raw.githubusercontent.com/github/spec-kit/main/templates/spec-template.md
- https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/analyze.md
- https://raw.githubusercontent.com/github/spec-kit/main/templates/commands/converge.md
- https://raw.githubusercontent.com/github/spec-kit/main/docs/reference/presets.md
- https://github.com/github/spec-kit/blob/main/extensions/RFC-EXTENSION-SYSTEM.md
- https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
- https://kiro.dev/docs/specs/
- https://kiro.dev/docs/specs/feature-specs/
- https://kiro.dev/docs/specs/best-practices/
- https://kiro.dev/docs/getting-started/first-project/
- https://kiro.dev/docs/steering/
- https://kiro.dev/docs/cli/acp/
- https://kiro.dev/blog/introducing-kiro/
- https://kiro.dev/blog/kiro-adopts-acp/
- https://github.com/kirodotdev/Kiro
- https://github.com/kirodotdev/Kiro/issues/8859
- https://deepwiki.com/kirodotdev/Kiro
- https://visualstudiomagazine.com/articles/2025/07/21/forked-again-awss-kiro-latest-ai-assistant-based-on-vs-code.aspx
- https://docs.tessl.io/use/spec-driven-development-with-tessl
- https://github.com/tesslio/spec-driven-development-tile
- https://raw.githubusercontent.com/tesslio/spec-driven-development-tile/main/docs/spec-format.md
- https://raw.githubusercontent.com/tesslio/spec-driven-development-tile/main/docs/spec-styleguide.md
- https://raw.githubusercontent.com/tesslio/spec-driven-development-tile/main/skills/spec-writer/SKILL.md
- https://raw.githubusercontent.com/tesslio/spec-driven-development-tile/main/skills/spec-verification/SKILL.md
- https://docs.tessl.io/reference/configuration
- https://docs.tessl.io/reference/cli-commands
- https://docs.tessl.io/use/tile-to-plugin-migration
- https://docs.tessl.io/introduction-to-tessl/how-tessl-works
- https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (author: Birgitta Bockeler, 2025-10-15)
- https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry/ (2025-09-23)
- https://tessl.io/blog/spec-driven-development-10-things-you-need-to-know-about-specs/ (author: Patrick Debois, 2025-10-29)
- https://tessl.io/registry/tessl-labs/spec-driven-development
- https://alistairmavin.com/ears/
- https://en.wikipedia.org/wiki/Easy_Approach_to_Requirements_Syntax
- https://ccy05327.github.io/SDD/08-PDF/Easy%20Approach%20to%20Requirements%20Syntax%20(EARS).pdf
- https://my.infocaptor.com/hub/summaries/ai-engineer/the-new-code-sean-grove-openai-8rABwKRsec4
- https://www.classcentral.com/course/youtube-the-new-code-sean-grove-openai-467279
- https://www.implicator.ai/the-end-of-coding-how-specifications-are-becoming-the-new-source-code/
- https://www.thoughtworks.com/radar/techniques/spec-driven-development
- https://www.thoughtworks.com/insights/blog/agile-engineering-practices/spec-driven-development-unpacking-2025-new-engineering-practices
- https://thoughtworks.medium.com/spec-driven-development-d85995a81387
- https://addyosmani.com/blog/good-spec/
- https://www.oreilly.com/radar/how-to-write-a-good-spec-for-ai-agents/
- https://simonw.substack.com/p/agentic-engineering-patterns
- https://www.hillelwayne.com/pbt-contracts/
- https://www.hillelwayne.com/talks/beyond-unit-tests/
- https://cacm.acm.org/research/how-amazon-web-services-uses-formal-methods/
- https://lamport.azurewebsites.net/tla/formal-methods-amazon.pdf
- https://brooker.co.za/blog/2015/03/29/formal.html
- https://en.wikipedia.org/wiki/TLA+
- https://en.wikipedia.org/wiki/Literate_programming
- https://en.wikipedia.org/wiki/Web_(programming_system)
- http://www.literateprogramming.com/knuthweb.pdf
- https://arxiv.org/abs/2602.00180
- https://github.com/ChrysKoum/SpecSync
- https://medium.com/@wasowski.jarek/living-documentation-in-sdd-spec-drift-6-traps-and-the-sync-owner-gate-mechanism-74b706c9db95
- https://www.kinde.com/learn/ai-for-software-engineering/ai-devops/spec-drift-the-hidden-problem-ai-can-help-fix/
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://en.wikipedia.org/wiki/Spec-driven_development
- https://github.com/bmad-code-org/bmad-method
- https://docs.bmad-method.org/
- https://medium.com/@mariussabaliauskas/a-comparative-analysis-of-ai-agentic-frameworks-bmad-method-vs-github-spec-kit-edd8a9c65c5e
- https://agents.md/
- https://docs.factory.ai/cli/configuration/agents-md
- https://docs.cursor.com/context/rules
- https://thepromptshelf.dev/blog/windsurfrules-complete-guide-2026/
- https://dev.to/idavidov13/one-file-to-rule-them-all-cursor-windsurf-and-vs-code-hh2
- https://developers.googleblog.com/conductor-introducing-context-driven-development-for-gemini-cli/
- https://grokipedia.com/page/Conductorbuild
- https://www.augmentcode.com/blog/intent-a-workspace-for-agent-orchestration
- https://www.augmentcode.com/tools/intent-vs-conductor-macos-agent-orchestrators
- https://www.augmentcode.com/tools/best-spec-driven-development-tools
- https://www.augmentcode.com/tools/best-kiro-alternatives
- https://github.com/eyaltoledano/claude-task-master
- https://www.taskmaster.one/
- https://medium.com/@richardhightower/agentic-coding-gsd-vs-spec-kit-vs-openspec-vs-taskmaster-ai-where-sdd-tools-diverge-0414dcb97e46
- https://github.com/stanfordnlp/dspy
- https://arxiv.org/abs/2310.03714
- https://arxiv.org/abs/2402.13521
- https://arxiv.org/pdf/2505.09027
- https://github.com/pr-pm/prpm
- https://docs.prpm.dev/introduction
- https://www.marktechpost.com/2026/05/08/9-best-ai-tools-for-spec-driven-development-in-2026-kiro-bmad-gsd-and-more-compare/
- git ref befd889 (HEAD) — `git show befd889:harness/harness.md` (the thesis, two-zone model, intake, unattended build, generate.py front-end equivalence)
- git ref befd889 — `git show befd889:spec/constitution.md` (Version 1.0.0; rules C-ENV-STRIP, C-FINALIZE, C-MAXITER, C-ACTION-SAFETY, C-SESSION-SCOPE, C-EARS-EVAL-BOUND, C-OUTCOME-EVAL, C-TWO-TURN, C-NO-FALSE-PASS, etc., each '-> enforced by' a mechanical owner; changelog cites recovered rules from archaeology + competitive critique)
- git ref befd889 — `git show befd889:harness/workflows/gates.md` (31.8KB; the 8-check DEMO table, demo_gate.sh, eval_lint.py AST source, gate_eval.py judge-stability source, the 4-check PROD table, prod-gate Makefile)
- git ref befd889 — `git show befd889:harness/workflows/build.md` (25.7KB; intake 4-Q table, §2a 6-check pre-flight, §2b single approval, §3 generate manifest with sessions.py/guardrails.py DISCRIMINATOR + the GOAL/CRITERION sync warnings)
- git ref befd889 — `git show befd889:harness/agents/drift-auditor.md` (intent-authoritative reconciliation, RECORD vs FLAG by kind, OpenSpec-style delta record to reports/drift/<date>-<branch>.yaml)
- `git ls-tree -r --name-only befd889` — confirms the full harness file tree AND that NO reports/archaeology/*, SPEC-RECONCILIATION.md, COMPETITIVE-RESEARCH.md, or HARDENING-LOG file is tracked (only reports/sessions/.gitkeep) => those repeated cross-references dangle
- git ref d6def4a (branch feature/data-analysis-2026-06-20) — commit msg 'build: data analysis agent — gate exits 0 (all 8 checks pass)'; `git show d6def4a --stat` = 40 files / 4,045 insertions (full agent/ package incl. sessions.py + guardrails.py, uv.lock); `git show d6def4a:spec/capabilities/file-analysis.md` = the live EARS + [@eval] + ## Evaluation format
- git ref d6def4a — `git show d6def4a:tests/test_file_retention.py` line 12 `def test_file_retention` => the [@eval: tests/test_file_retention.py::test_file_retention] token resolves to a real case
- git refs 875fd41, c85e982 (branch feature/support-triage-2026-06-20) — `git diff --stat befd889 c85e982` = 47 files / 3,353 insertions incl. ui/ (Next.js); c85e982 commit body = keyless gate verification (eval_lint exit 0, 14 passed + 1 key-gated skip, boot smoke ok)
- git ref c85e982 — `git show c85e982:README.md` (non-coder-facing quick-start: .env keys, port 8001, make setup/dev/gate, P1 live + P2/P3 deterministic stubs framing)
- Prose-volume measurement via `git show befd889:<file> | wc -c`: gates.md 31,801; build.md 25,751; constitution.md 12,767; harness.md 6,979 bytes — quantifies the over-long re-typed-prose failure
