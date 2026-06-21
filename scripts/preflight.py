#!/usr/bin/env python3
"""Pre-flight check — run before a build or demo to catch missing tools and config."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

OK   = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

errors = 0


def check(label: str, *, cmd: str | None = None, condition: bool | None = None) -> bool:
    global errors
    passed = condition if condition is not None else _run(cmd)
    if passed:
        print(f"{OK} {label}")
    else:
        print(f"{FAIL} {label}")
        errors += 1
    return passed


def warn(label: str, *, cmd: str | None = None, condition: bool | None = None) -> bool:
    passed = condition if condition is not None else _run(cmd)
    if passed:
        print(f"{OK} {label}")
    else:
        print(f"{WARN} {label}  (optional — some features won't work)")
    return passed


def _run(cmd: str) -> bool:
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _python_version_ok() -> bool:
    return sys.version_info >= (3, 12)


def _env_key_set(key: str) -> bool:
    env = ROOT / ".env"
    if not env.exists():
        return False
    return any(line.startswith(f"{key}=") and len(line.split("=", 1)[1].strip()) > 0
               for line in env.read_text().splitlines())


print()
print("=== SDD Agent Harness — Pre-flight Check ===")
print()

# --- Required tools ---
print("Tools:")
check("git",            cmd="git --version")
check("python 3.12+",  condition=_python_version_ok())
check("uv",            cmd="uv --version")
check("claude CLI",    cmd="claude --version")

print()

# --- Repo state ---
print("Repo:")
check("inside a git repo",  cmd="git rev-parse --git-dir")
check(".env file exists",   condition=(ROOT / ".env").exists())

print()

# --- API keys (read from spec/rules/tech-stack.md to know what's required) ---
# Default required keys for a Python + LangGraph + FastAPI build.
# Update this list to match your project's spec/rules/tech-stack.md.
print("API keys (edit this script to match your project):")
warn("LLM key present",  condition=any(
    _env_key_set(k) for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"]
))

print()

# --- Python environment ---
print("Python env:")
venv = ROOT / ".venv"
if venv.exists():
    check(".venv exists", condition=True)
else:
    print(f"{WARN} .venv not found — run: uv sync")
    errors += 1

print()

# --- Directory structure ---
print("Directories:")
for d in ["src", "tests", "logs/sessions"]:
    path = ROOT / d
    path.mkdir(parents=True, exist_ok=True)
    check(f"{d}/ exists", condition=True)

print()

if errors == 0:
    print("=== All checks passed. Ready to build. ===")
else:
    print(f"=== {errors} issue(s) found — fix before proceeding. ===")
    sys.exit(1)

print()
