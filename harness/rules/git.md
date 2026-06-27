# Git Discipline

All git rules that apply to every Claude Code session in this repo.

---

## Branch Model

- **`main` is boilerplate-only.** Never commit application code to `main`. Only spec/harness/boilerplate improvements (no app code) reach `main`, via a reviewed PR.
- **Branch every build from `main`.** Always `git checkout main && git checkout -b feature/<slug>-v0.1` — builds always start from the stable main base, never from an experimental harness branch. This keeps every generated app isolated from in-progress harness changes.
- **The build's PR targets `main`.** Open it with `--base main` so the PR is reviewable against the canonical base. App code is never merged to main — the PR exists for review and dogfood record only.
- All phase commits go to the feature branch, never to `main`
- When the build is complete, open the PR from the feature branch into `main` — do not merge locally
- If you find yourself on `main` while writing application code, stop immediately, create the feature branch, and continue there

---

## Commit + Push Are One Atomic Action

**Every commit must be pushed immediately.** `git commit` and `git push` are a single atomic action — never one without the other.

```bash
git commit -m "phase-N: what you did" && git push origin <branch>
```

A commit that is not pushed does not exist as far as the project is concerned. This is not optional and survives context compression — if you remember only one rule: **commit then push, every time, no exceptions.**

---

## PR Must Exist Before the First Feature-Branch Commit

After creating the feature branch and pushing the first commit, immediately open a PR — based on `<base>` (the branch you cut from, captured at branch time), not `main`:

```bash
git checkout main                          # always start from clean main
git checkout -b feature/<slug>-v0.1
# ... first commit + push ...
gh pr create --base main --head feature/<slug>-v0.1
```

Every subsequent `git push` automatically updates the same PR. Pushing commits without an open PR is equivalent to committing without pushing: the work is invisible and unreviewable.

---

## Before Every Reply to the User

1. Run `git status`
2. If dirty: commit and push with `git commit -m "..." && git push origin <branch>`
3. Confirm the working tree is clean **and** the branch is pushed before replying

---

## Commit Message Format

```
phase-N: [what you did]
```

Examples:
- `phase-1: add domain models`
- `phase-2: stub agent loop end-to-end`
- `harness: add git discipline doc`

The diff shows the *what*. The message answers: *why was this change needed, and what is the outcome?*

---

## Staging Rules

- **Never `git add -A` or `git add .`** — always stage specific files or directories. `-A` sweeps in untracked leftovers from prior build attempts (stray packages, abandoned experiments) and poisons the commit.
- If a phase needs many files, list them explicitly or stage directories one at a time.
- Run `git diff --staged` before every commit. You are responsible for what you push.

---

## Commit Quality

- **Commits are logical units.** Each commit should be a self-contained, reviewable change. "Fix bug and refactor and add feature" is three commits.
- **No commented-out code in commits.** If code is not needed, delete it. Git history preserves it.
- **Never commit secrets** — no API keys, passwords, or tokens in source files. See `harness/rules/secret-hygiene.md`. The `.env` containing API keys is the only manual user step and must stay gitignored — `.env.example` is committed, `.env` is never staged.
- **Never force-push without explicit user confirmation.**

---

## PR Description

Every PR needs:
- What changed
- Why
- How to verify

Screenshots or test output for UI/behavioural changes.

---

## Phase Gate: Git Checklist

A phase is not complete until:
- [ ] All code for the phase is committed
- [ ] Commit is pushed to the feature branch
- [ ] Working tree is clean (`git status` shows nothing)
- [ ] Phase test-handoff published; for a build, the human has tested and approved the phase

To see phase history: `git log --oneline | grep "phase-"`

---

## Closing a Session

Before ending any session:
- [ ] Working tree is clean (all changes committed and pushed)
- [ ] Branch is up to date with remote
