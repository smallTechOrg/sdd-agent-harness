#!/usr/bin/env python3
"""Reset the repo to a clean boilerplate state for a new build.

Wipes all project-generated output: src/, tests/, migrations, lockfile,
virtualenv, and logs. Spec templates and harness are untouched.

Safe to run between workshop iterations or before starting a fresh build.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def remove(path: Path) -> None:
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"  removed  {path.relative_to(ROOT)}")
    else:
        print(f"  skip     {path.relative_to(ROOT)}  (not found)")


print()
print("=== SDD Agent Harness — Reset to Boilerplate ===")
print()
print("This will remove:")
print("  src/         application code")
print("  tests/       test suite")
print("  alembic/     migrations")
print("  pyproject.toml, uv.lock, .venv/")
print("  spec/features/*  (FR and CR files)")
print("  logs/sessions/*, logs/runtime/*, logs/analysis/*")
print()

if not confirm("Proceed?"):
    print("Aborted.")
    sys.exit(0)

print()
print("Cleaning...")

# Generated project code
for p in ["src", "tests", "alembic", "pyproject.toml", "uv.lock", ".venv"]:
    remove(ROOT / p)

# Feature requests and change requests (keep the folder, wipe files)
features = ROOT / "spec" / "features"
if features.exists():
    for f in features.iterdir():
        if f.name != ".gitkeep":
            remove(f)
    print(f"  cleared  spec/features/  (kept .gitkeep)")

# Logs (keep folder structure, wipe contents)
for subdir in ["sessions", "runtime", "analysis"]:
    log_dir = ROOT / "logs" / subdir
    log_dir.mkdir(parents=True, exist_ok=True)
    for f in log_dir.iterdir():
        if f.name != ".gitkeep":
            remove(f)
    print(f"  cleared  logs/{subdir}/")

print()
print("=== Reset complete. Repo is back to boilerplate state. ===")
print()
print("Next steps:")
print("  git checkout -b feat/your-agent-name")
print("  claude")
print("  /build")
print()
