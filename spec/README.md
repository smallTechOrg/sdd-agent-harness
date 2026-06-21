# spec/ — the intention layer

The human-authored contract for this project. All code must match this spec; when they
disagree, spec wins — fix the code. The researcher authors it; the supervisor signs it
off. See [../harness/README.md](../harness/README.md) for the full SDD method.

```
spec/
  rules/        project-specific rule overrides (on top of harness/rules/)
  features/     what the system should do — vision, architecture, capabilities
  patterns/     how to build it — tech stack, code style, framework choices
```

---

## rules/

Project-specific overrides on top of [harness/rules/](../harness/rules/).
Empty until this project needs to diverge from the harness defaults.

## features/

What the system should be. The researcher fills these in; they are the source of truth
for product intent. Code conforms to features, never the reverse.

- [features/vision.md](features/vision.md) — purpose, goals, success criteria
- [features/architecture.md](features/architecture.md) — system design, layers, data flow
- [features/data-model.md](features/data-model.md) — data schema
- [features/api.md](features/api.md) — API surface
- [features/ui.md](features/ui.md) — UI requirements
- [features/agent-graph.md](features/agent-graph.md) — agent graph (LangGraph/etc. projects)

To add a capability: add a file to `features/`. One file = one discrete feature.

## patterns/

How to build it — stack choices, code conventions, framework-specific rules. The generic
and agentic patterns live in [harness/patterns/](../harness/patterns/).

- [patterns/tech-stack.md](patterns/tech-stack.md) — language, framework, DB, deploy target
- [patterns/code-style.md](patterns/code-style.md) — style rules, framework gotchas

---

## Governance

1. **Spec first** — no `src/` change without a backing spec change.
2. **One fact, one place** — never duplicate across files; cross-reference with links.
3. **`features/` = WHAT, `patterns/` = HOW** — no implementation detail in features.
4. **Update spec before code** — if requirements change, spec changes first.
