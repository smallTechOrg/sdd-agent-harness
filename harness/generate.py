#!/usr/bin/env python3
"""Generate the Claude Code front-ends from the single canonical source (`harness/`).

CLAUDE.md, `.claude/agents/`, and `.claude/commands/` are GENERATED — never edit them by hand. Edit
`harness/` and re-run `python harness/generate.py`. This repo targets Claude Code only: the sub-agent and
workflow source files carry Claude Code frontmatter (name/description/tools for subagents; a slash-command
description for commands), and that frontmatter is kept on line 1 so the files load as real Claude Code
subagents and slash commands.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
BANNER = "<!-- GENERATED from harness/ — do not edit; run `python harness/generate.py` -->\n\n"

ENTRY = BANNER + """# Claude Code — Entry Point

**First action: read [`harness/harness.md`](harness/harness.md)** — the operating manual. Then read the
spec in `spec/` if it is filled in; otherwise run `/build "<your idea>"`.

## What this repo is
A frontier spec-driven harness that builds a production agentic AI agent from a spec. Claude Code generates
the agent fresh from the recipes in `harness/patterns/` (current library versions), gated by mechanical
checks. Nothing is a frozen app — the harness ships knowledge, not lock-in.

## Map
- `harness/harness.md` — the rules · `harness/workflows/` — procedures (/build, /deploy, …)
- `harness/agents/` — sub-agent roles · `harness/patterns/` — the frontier code recipes (all 11 layers)
- `.claude/agents/` — those roles as Claude Code subagents · `.claude/commands/` — those workflows as slash commands
- `spec/` — the 4-file input contract you fill · `.githooks/` — mechanical guardrails

A funded `APP_LLM_API_KEY` is required for a real run.
"""


def _emit(src: str) -> str:
    """Banner a generated file while keeping any YAML frontmatter on line 1. Claude Code requires the
    `---` block first in subagent/command files, so the banner goes immediately after it."""
    if src.startswith("---\n"):
        close = src.find("\n---\n", 4)
        if close != -1:
            cut = close + len("\n---\n")
            return src[:cut] + "\n" + BANNER + src[cut:].lstrip("\n")
    return BANNER + src


def _targets() -> list[tuple[Path, str]]:
    """The (path, expected-content) pairs generate.py owns — the single source of the harness→.claude map."""
    out: list[tuple[Path, str]] = [(ROOT / "CLAUDE.md", ENTRY)]
    for a in sorted((HARNESS / "agents").glob("*.md")):
        out.append((ROOT / ".claude" / "agents" / a.name, _emit(a.read_text())))
    for w in sorted((HARNESS / "workflows").glob("*.md")):
        out.append((ROOT / ".claude" / "commands" / w.name, _emit(w.read_text())))
    return out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print("wrote", path.relative_to(ROOT))


def check() -> int:
    """Mechanical owner of the harness→front-end equivalence: exit 0 iff every generated file on disk matches
    what generate.py would emit from harness/. A stale .claude/ (the rules a user reads diverging from the
    rules the authors edit) is a BUILD-BLOCKING failure, wired into .githooks/pre-commit (HARDENING-LOG iter 6)."""
    stale = [p for p, text in _targets()
             if not p.exists() or p.read_text() != text]
    if stale:
        print("STALE Claude Code front-ends — run `python harness/generate.py` and commit the result:",
              file=sys.stderr)
        for p in stale:
            print(f"  {p.relative_to(ROOT)}", file=sys.stderr)
        return 1
    print("generate-check: .claude/ + CLAUDE.md are in sync with harness/ ✓")
    return 0


def main() -> None:
    targets = _targets()
    for path, text in targets:
        _write(path, text)
    print(f"generated Claude Code front-ends from harness/ ({len(targets) - 1} files + CLAUDE.md)")


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        sys.exit(check())
    main()
