#!/usr/bin/env bash
# Push to remote whenever local commits are ahead of upstream.
# Runs as a PostToolUse hook on Bash.

if git rev-parse --abbrev-ref --symbolic-full-name @{u} &>/dev/null; then
  ahead=$(git rev-list @{u}..HEAD --count 2>/dev/null)
  if [ "$ahead" -gt 0 ]; then
    git push 2>&1
  fi
fi
