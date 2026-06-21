# Project Layout

The repository root holds the four layers (`spec/`, `src/`, `logs/`, `harness/`) plus the
`.claude/` adapter and project config. These conventions are language-neutral; the
concrete, per-project choices live in `spec/engineering/tech-stack.md`, and stack-specific
footguns live in `../knowledge/gotchas.md`.

## Where things go

- **All application source code lives in `src/`.** Never at the repo root — for every
  stack (backend packages, web UI, scripts, data).
- **Tests live in `tests/` at the repo root**, not inside `src/`.
- **Runtime behavior is written to `logs/`** — never committed if it contains live data
  (`*.log` is git-ignored); structured logs go to `logs/runtime/`.
- **The spec is the contract.** `src/` conforms to `spec/`, never the reverse.

## Repo skeleton

```
spec/        goal     — human-authored intent (product/ + engineering/)
src/         action   — the code (one package/module per concern)
logs/        outcome  — sessions/ (journals), runtime/, analysis/
harness/     method   — rules/, method/, knowledge/, roles/, workflows/  (source of truth)
.claude/     adapter  — settings, hooks, rules shim, agents, skills
CLAUDE.md    entry    — thin pointer into harness/
README.md             — what this project is
```

## Rules

1. Application code in `src/`; tests in `tests/`; never at the root.
2. One concern per package/module; no god-files.
3. Prompts and templates are data files loaded at runtime, not inlined in code.
4. External services (LLM, DB, APIs) sit behind a thin client/abstraction, never called
   raw from business logic.
5. The skeleton phase must run fully offline (stubs, no keys, no network).

The concrete stack — language, framework, database, UI, deploy target, default port,
model names — is chosen by the researcher/architect and recorded in
`spec/engineering/tech-stack.md`.
