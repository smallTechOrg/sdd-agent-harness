# spec/ — the intention layer

The human-authored contract for this project. All code must match this spec; when they
disagree, spec wins — fix the code. The researcher authors it; the supervisor signs it
off. See [../harness/README.md](../harness/README.md) for the full SDD method.

```
spec/
  rules/        constraints — tech stack, code style, rule overrides
  features/     what the system should do — vision, architecture, capabilities
  patterns/     reusable patterns + version-pinned usage-specs (one file per lib, flat)
```

---

## rules/

Hard constraints for this project. The researcher fills these in at intake.

- [rules/tech-stack.md](rules/tech-stack.md) — language, framework, DB, deploy target
- [rules/code-style.md](rules/code-style.md) — style rules, framework gotchas

Any overrides to [harness/rules/](../harness/rules/) also live here.

## features/

One file per discrete request. Empty until work begins.

- **FR-NNN-title.md** — feature request, created during `/build`
- **CR-NNN-title.md** — change request, created during `/fix`

The researcher authors these; the supervisor signs them off before any code is written.

## ROADMAP.md

Deferred scope and future ideas — two tiers:
- **`proposed` FRs** in `features/` (fully specced, waiting for user approval after the core ships)
- **Parked ideas** in `spec/ROADMAP.md` (directional, not yet concrete enough to spec)

No idea gets dropped. The 30-minute build ceiling is hard; anything that would push past it is
named here or in a `proposed` FR — never a vague "later."

## patterns/

**Usage-specs only** — version-pinned API-shape guardrails, one short file per library the
project pins (correct/forbidden shapes for *that* version), so a generated seam can't drift
onto a wrong-version call. These are **project artefacts**: they belong here because the libs
and versions are this project's choice. Established at intake; refreshed when a feature bumps
a pinned lib (see [harness/recipes/README.md](../harness/recipes/README.md) → re-sync convention).

Method patterns (engineering, observability, UX, LLM, agentic) live in `harness/patterns/` —
not here.

Files: `fastapi.md`, `langgraph.md`, `langchain-core.md`, `google-genai.md`,
`sqlalchemy-async.md`, `pydantic-settings.md`, `nextjs.md`.

---

## Governance

1. **Spec first** — no `src/` change without a backing spec change.
2. **One fact, one place** — never duplicate across files; cross-reference with links.
3. **`features/` = WHAT, `rules/` = HOW + constraints** — no implementation detail in features.
4. **Update spec before code** — if requirements change, spec changes first.
