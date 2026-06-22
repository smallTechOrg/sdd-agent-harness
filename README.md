# AI Agent Boilerplate — Spec-Driven, Zero-Shot to Working Agent

This is a boilerplate for building AI agents spec-first. Give it a one-line idea. Walk away with a working, tested, phased agent.

---

## What This Is

A starting point for anyone who wants to build an AI agent without writing boilerplate from scratch. The repo ships with:

- A structured **spec template** covering product vision, architecture, capabilities, data model, API, and UI
- Three **zero-shot skills** (`/zero-shot-build`, `/zero-shot-fix`, `/zero-shot-sync`), each also available as a slash command
- A five-agent **team** — agent-builder orchestrates (and owns git/PR) spec-writer, tech-architect, code-generator, and qa-auditor; the code maker is paired with an independent checker (qa-auditor reviews *and* runs), spec and tech design self-review
- Engineering rules in `harness/` so every Claude Code session is consistent
- Phase-gated implementation — minimal working thing first, then iterative expansion
- Autonomous after a single intake round: one prompt → a thoroughly-tested agent with no further interaction
- Real-key testing — every phase gate runs against the live LLM/API using keys from `.env`

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

`/zero-shot-build` asks a short round of intake questions up front — including which API keys to put in `.env` — then runs fully autonomously to a tested, working agent with no further interaction.

---

## What Happens Next (Intake, Then Fully Automated)

`/zero-shot-build` runs one intake round, then hands off to the **agent-builder**, which coordinates the team:

```
Your idea
    ↓
INTAKE — scope, stack, trigger, constraints; fill .env with the required API keys
         (may ask extra clarifying questions up front)
    ↓
[spec-writer]    → Drafts AND self-reviews the product spec (ruthless MVP scope)
    ↓
[tech-architect] → Designs AND reviews stack / architecture / agent / plan
    ↓
[agent-builder]  → Feature branch + PR before the first commit
    ↓
per phase:  [code-generator] → [qa-auditor] → [agent-builder]
            write code+tests    review + run    commit+push
            ↑______ loop until reviewed clean AND VERIFIED ______↑
    ↓
[qa-auditor]     → Final spec↔code drift audit (CLEAN before hand-off)
    ↓
Hand-off to you
```

**Nothing is skipped.** A phase stays open until qa-auditor's code review is clean and it returns VERIFIED — meaning edge-case, end-to-end, and UI tests pass against the real LLM/API using keys from `.env`, "perfect, zero errors" (~20-30 min to a thoroughly-tested agent). After the build, fix bugs with `/zero-shot-fix` and keep spec and code aligned with `/zero-shot-sync`.

---

## Development Phases (Default Model)

| Phase | What Gets Built |
|-------|-----------------|
| 1 | Domain models + data layer |
| 2 | Core agent loop wired to the real LLM (keys from `.env`); integrations stubbed only where the external system itself isn't built yet |
| 3 | First real integration (the "happy path" end-to-end, real keys) |
| 4 | Error handling, retries, resilience |
| 5 | Remaining integrations |
| 6 | API / CLI surface |
| 7 | Basic UI (if needed) — UI tests required when a UI exists |
| 8 | Integration + edge-case + end-to-end tests (real keys) |
| 9 | Observability + logging |
| 10 | Polish, documentation, hand-off |

Each phase ends with a commit and passes QA before the next phase begins.

---

## Repo Layout

```
.claude/
  skills/           ← Entry points (/zero-shot-build, /zero-shot-fix, /zero-shot-sync) — source of truth
  commands/         ← Thin slash-command aliases that defer to the skills
  agents/           ← The team, one full self-contained definition each (agent-builder, spec-writer, tech-architect, code-generator, qa-auditor)
spec/               ← The product — what your agent does (you read & edit this)
  roadmap.md        ← Purpose, goals, success criteria
  architecture.md   ← System design + the chosen ## Stack
  agent.md          ← This agent's graph (if a framework is used)
  data.md  api.md  ui.md
  capabilities/     ← One file per discrete capability
harness/            ← How Claude Code should build, generically (doctrine the skills/agents cite)
  rules/            ← Mandatory rules (ai-agents, git, secret-hygiene)
  patterns/         ← phases, test-driven, project-layout, tech-stack, code, agentic-ai, …
reports/
  sessions/         ← Auto-generated session logs from every AI coding session
CLAUDE.md           ← Entry point for Claude Code
.env.example        ← Environment variable template
```

---

## Manually Editing the Spec

If you prefer to write the spec yourself before involving AI:

1. Open `spec/roadmap.md` and fill in the placeholders
2. Work through each file in `spec/` in order
3. Once the spec is complete, run `/zero-shot-build` — it sees the filled-in spec and goes straight to planning and building

---

## Rules That AI Agents Follow

Every Claude Code session in this repo follows the rules in `harness/rules/ai-agents.md`:

- Read the full spec before writing any code
- Open a session report at `reports/sessions/`
- Commit every logical unit of work (never accumulate uncommitted changes)
- One phase at a time — no skipping
- Write tests before marking a phase complete
- Tests and evals run against the real LLM/API using keys from `.env` — offline/stubbed runs are not a passing gate
- The build is non-interactive after intake — questions are asked once, up front
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

This is a boilerplate, not a framework. Improvements to the spec templates, engineering rules, agent definitions, or skills belong on `main`; generated application code does not (see Test-Branch Workflow above).
