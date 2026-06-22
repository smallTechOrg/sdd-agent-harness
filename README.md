# AI Agent Boilerplate — Spec-Driven, Zero-Shot to Working Agent

This is a boilerplate for building AI agents spec-first. Give it a one-line idea. Walk away with a working, tested, phased agent.

---

## What This Is

A starting point for anyone who wants to build an AI agent without writing boilerplate from scratch. The repo ships with:

- A structured **spec template** covering product vision, architecture, capabilities, data model, API, and UI
- Three **zero-shot skills** (`/zero-shot-build`, `/zero-shot-fix`, `/zero-shot-sync`), each also available as a slash command
- An eight-agent **team** — agent-builder orchestrates spec-writer, spec-reviewer, tech-architect, code-generator, code-reviewer, qa-auditor, and deployer (makers paired with checkers)
- Engineering rules in `harness/` so every Claude Code session is consistent
- Phase-gated implementation — minimal working thing first, then iterative expansion

---

## How to Use This

### Step 1 — Clone and configure

```bash
git clone https://github.com/smallTechOrg/ai-spec-driven-boilerplate.git my-agent
cd my-agent
cp .env.example .env
```

### Step 2 — Open in Claude Code (or any AI coding assistant)

```bash
claude
```

### Step 3 — Kick off the build with your idea

```
/zero-shot-build An agent that monitors my Shopify store for low-inventory products and automatically drafts restock emails to suppliers
```

`/zero-shot-build` asks 4 questions up front, then runs autonomously to a working skeleton.

---

## What Happens Next (Intake, Then Automated)

`/zero-shot-build` runs intake + approval, then hands off to the **agent-builder**, which coordinates the team:

```
Your idea
    ↓
INTAKE — 4 questions (scope, stack, trigger, constraints)          [skill]
    ↓
[spec-writer]    → Drafts the product spec (ruthless MVP scope)
[spec-reviewer]  → Independent review → back to spec-writer on blockers
    ↓
[tech-architect] → Designs AND reviews stack / architecture / agentic-ai / plan
    ↓
ONE APPROVAL — you see scope + stack + plan; approve once          [skill]
    ↓
[deployer]       → Feature branch + PR before the first commit
    ↓
per phase:  [code-generator] → [code-reviewer] → [qa-auditor] → [deployer]
            write code+tests    critique         run gates       commit+push
            ↑___________ loop until reviewed clean AND VERIFIED ___________↑
    ↓
[qa-auditor]     → Final spec↔code drift audit (CLEAN before hand-off)
    ↓
Hand-off to you
```

**Nothing is skipped.** A phase stays open until code-reviewer is clean and qa-auditor returns VERIFIED. After the build, fix bugs with `/zero-shot-fix` and keep spec and code aligned with `/zero-shot-sync`.

---

## Development Phases (Default Model)

| Phase | What Gets Built |
|-------|-----------------|
| 1 | Domain models + data layer |
| 2 | Core agent loop (no integrations, stubbed tools) |
| 3 | First real integration (the "happy path" end-to-end) |
| 4 | Error handling, retries, resilience |
| 5 | Remaining integrations |
| 6 | API / CLI surface |
| 7 | Basic UI (if needed) |
| 8 | Integration tests |
| 9 | Observability + logging |
| 10 | Polish, documentation, hand-off |

Each phase ends with a commit and passes QA before the next phase begins.

---

## Repo Layout

```
.claude/
  skills/           ← Entry points (/zero-shot-build, /zero-shot-fix, /zero-shot-sync) — source of truth
  commands/         ← Thin slash-command aliases that defer to the skills
  agents/           ← The team (agent-builder, spec-writer, spec-reviewer, tech-architect, code-generator, code-reviewer, qa-auditor, deployer)
spec/               ← What your agent does (fill this in or let /zero-shot-build do it)
  capabilities/     ← One file per discrete capability
  tech-stack.md     ← Language, framework, libraries
  code-style.md     ← Style and structural rules
harness/            ← How Claude Code should build for this project (immutable rules)
  workflows/        ← Step-by-step procedures for each agent/workflow type
reports/
  sessions/         ← Auto-generated session logs from every AI coding session
CLAUDE.md           ← Entry point for Claude Code
.env.example        ← Environment variable template
```

---

## Manually Editing the Spec

If you prefer to write the spec yourself before involving AI:

1. Open `spec/vision.md` and fill in the placeholders
2. Work through each file in `spec/` in order
3. Once the spec is complete, run `/zero-shot-build` — it sees the filled-in spec and goes straight to planning and building

---

## Rules That AI Agents Follow

Every Claude Code session in this repo follows the rules in `harness/ai-agents.md`:

- Read the full spec before writing any code
- Open a session report at `reports/sessions/`
- Commit every logical unit of work (never accumulate uncommitted changes)
- One phase at a time — no skipping
- Write tests before marking a phase complete
- Update this README whenever the project layout changes

---

## FAQ

**What if my agent needs a database?**
The spec template includes a data model section. The tech-architect sub-agent will recommend the right database for your use case.

**What if I already have a tech stack in mind?**
Say it in the idea: `/zero-shot-build [idea] — use Python + FastAPI + PostgreSQL`. The tech-architect honors stated stack choices as binding and skips those questions.

**What if something breaks?**
Run `/zero-shot-fix [what's broken]` — it classifies the problem (bug, error, failing test, or drift), fixes it with spec context, and verifies. The qa-auditor catches phase failures before the next phase starts.

---

## Test-Branch Workflow

The recommended way to iterate on this boilerplate:

1. Keep `main` as the clean boilerplate — only spec, engineering rules, and agent config.
2. For each build attempt, create a numbered test branch: `test-1`, `test-2`, etc.
3. Run `/zero-shot-build` with a single-line idea on the test branch. Let it build.
4. Review and test the result on that branch.
5. **Never merge the generated application code back to main.** Test branches are disposable.
6. If a run surfaces a boilerplate improvement (a clearer spec template, a missing rule), cherry-pick or manually apply that fix to `main`.

---

## Contributing

This is a boilerplate, not a framework. Improvements to the spec templates, engineering rules, agent definitions, or workflow specs belong on `main`. Generated application code does not.
