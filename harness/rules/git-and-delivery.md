# Git & Delivery

## Commit then push (hook-enforced)

`git commit` and `git push` are a single indivisible action. Use
`git commit -m "..." && git push origin <branch>`. A commit that is not pushed does not
exist. A hook enforces this (`.claude/hooks/`); do not rely on memory.

## Branches & PRs

- All code lives on a feature branch: `git checkout -b feature/<slug>`.
- Open the PR before the first feature-branch commit:
  `gh pr create --base main --head feature/<slug>`. Every later push updates it.
- Application code reaches `main` only through a reviewed PR — never merged locally.
- If you find yourself on `main` about to write new code, stop and branch.

## Hygiene

- Commit every logical unit of work; never let the tree stay dirty across a reply.
- **Never `git add -A` / `git add .`** — stage specific files or directories.
- Commit message format: `step-N: <what you did>` for build work; `fix: …`, `spec: …`,
  `harness: …` otherwise.
- Never commit secrets. Never force-push without explicit confirmation.

## Before every reply

1. `git status`.
2. If dirty, commit + push.
3. Confirm the tree is clean and the branch is pushed before replying.
