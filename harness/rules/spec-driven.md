# Spec-Driven Development

The spec is written before the code. No exceptions.

## Why

When code is written without a spec, parts of the system make inconsistent assumptions,
testing becomes guesswork, every AI session re-derives requirements, and scope creeps
silently. When the spec comes first, every session reads the same requirements, tests
derive from the spec, and "does this match the spec?" is a concrete, answerable question
the analyser can audit.

## What goes where

- **`spec/product/`** — WHAT the system does: behavior, users, data, APIs, UI.
- **`spec/engineering/`** — HOW this build is done: chosen stack, code style, project rules.
- **Not in the spec** — line-by-line implementation (that's `src/`), temporary
  workarounds, or session notes (those go in `logs/sessions/`).

## When requirements change

1. Update the spec first (researcher), with engineer feasibility and reviewer testability.
2. Then update `src/`.
3. The analyser confirms `logs/` reconciles with the amended spec.


## Spec vs. implementation conflicts

If the spec says X and the code does Y, the code is wrong — fix it. Exception: if the
spec itself is wrong, amend the spec (researcher + reviewer) first, then fix the code.
The analyser may *propose* spec amendments when outcome diverges from goal; the human and
reviewer approve them. The analyser never silently edits the goal.


## Exceptions

User's intention is supreme, and they should always be override this, by allowing spec to be generated from code. But make sure to ask them for explicit permission.

One such case is a brownfield codebase, in that case it is necessary to generate spec from the existing code and from that point onwards user can switch to spec driven development. Or in a case when the user is technically proficient, and they know the code they are changing.



