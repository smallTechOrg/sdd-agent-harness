# Spec-Driven Development

The rule (stated in `ai-agents.md` § 4): **the spec is always written before the code.** This file is
the *why* and the *how*.

## Why spec-first

When code is written without a spec, parts of the system make inconsistent assumptions, testing becomes
guesswork, each AI session re-derives requirements differently, and scope creeps silently. When the spec
comes first, every session reads the same requirements, tests derive from the spec, "does this match the
spec?" is a concrete question, and the drift-auditor can catch divergence.

## What goes where

- **Product spec (`spec/product/`)** — WHAT the agent does: behaviour, users, data, APIs/integrations,
  UI. No implementation details.
- **Engineering spec (`spec/engineering/`)** — HOW: tech stack, code style, error/secret/test handling,
  phases.
- **Not in the spec** — line-by-line implementation (that's the code), temporary workarounds, and
  session-specific notes (those go in session reports).

## When requirements change

1. Update the spec first. 2. Get the spec change reviewed (spec-reviewer or manual). 3. Then update the
code. 4. Run the drift-auditor to confirm code matches the updated spec.

Never update the code first and "update the spec later" — later never comes.

## Spec vs. code conflicts

If the spec says X and the code does Y, the **code** is wrong — fix it to match. Exception: if the spec
itself is wrong, update and re-review the spec first, then fix the code.

## Adding a capability

Use `/spec-new-capability [description]` or ask the spec-writer. Do not add capabilities by writing code
first and describing it after.
