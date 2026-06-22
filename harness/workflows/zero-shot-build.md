# Workflow: Zero-Shot Build

The procedure behind the `/zero-shot-build` skill. The skill is the live orchestrator; this file is the reference for what each stage does, who owns it, and the gates that apply. One prompt → working, verified skeleton.

## Team

`/zero-shot-build` (skill) runs intake + approval, then delegates to **agent-builder**, which coordinates the team:

| Stage | Agent | Output |
|-------|-------|--------|
| Spec | spec-writer → spec-reviewer | `spec/` filled, reviewed |
| Tech + plan | tech-architect (designs + self-reviews) | `tech-stack.md`, `code-style.md`, `agentic-ai.md`, `reports/implementation-plan.md` |
| Scaffold | deployer | branch + PR; orchestrator adds dirs, session report, `.env.example` |
| Build (per phase) | code-generator → code-reviewer → qa-auditor → deployer | code + tests, reviewed, VERIFIED, pushed |
| Ship | qa-auditor (drift) → deployer | CLEAN audit, PR updated |

## Stages

1. **Intake (skill).** One round, 4 questions via `AskUserQuestion` (scope, stack, trigger, constraints) → one-paragraph brief.
2. **Design (agent-builder).** spec-writer drafts → spec-reviewer must return APPROVED (loop on blockers) → tech-architect decides stack + writes the phased plan, self-reviewing against the spec.
3. **Approval (skill).** One summary (scope / deferred / stack / Phase 1+2 plan with gate commands) → one confirmation. The only gate before code.
4. **Scaffold.** deployer creates `feature/<slug>-v0.1`, first commit, and **opens the PR before any phase commit** (Rule 11). Project dir per `project-layout.md`; session report at `reports/sessions/YYYY-MM-DD-HHMMSS-[branch].md` before Phase 1; `.env.example`.
5. **Build.** For Phase 1 then Phase 2: code-generator implements that phase only → code-reviewer critiques (loop on blockers) → qa-auditor runs the gate + golden-path/live-server smoke returning VERIFIED/BLOCKED (loop on BLOCKED) → deployer commits + pushes. Never start phase N+1 before N is VERIFIED.
6. **Ship.** qa-auditor final whole-tree drift audit (CLEAN before hand-off) → deployer ensures the PR is current.

## Gates (never skipped)

- Spec is reviewed (spec-reviewer APPROVED) before tech design.
- Exactly one user approval gate (after design), then autonomous.
- Each phase: code-reviewer clean **and** qa-auditor VERIFIED before commit; offline (no LLM key) against the production DB driver.
- Final qa-auditor drift audit CLEAN before hand-off.

## Adding a capability

Same team, reduced: skip scope intake; spec-writer adds one `spec/capabilities/<name>.md` (+ update `index.md`) → spec-reviewer → tech-architect plans the incremental phase → build loop.
