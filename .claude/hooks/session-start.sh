#!/usr/bin/env bash
# SessionStart hook — surface the awareness ledger for continuity.
# stdout is injected into the session's starting context.

echo "SDD harness active. Canon: harness/  •  Rules: harness/rules/non-negotiables.md"

latest=$(ls -t logs/sessions/*.md 2>/dev/null | head -1)
if [ -n "$latest" ]; then
  echo "Most recent session report: $latest"
  echo "Read its 'Open / next' section before starting; continue or open a new report."
else
  echo "No session report yet — open logs/sessions/YYYY-MM-DD-HHMMSS-<branch>.md before writing code."
fi
