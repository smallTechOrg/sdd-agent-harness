"""Guardrails + per-run budget — input/output checks, hard caps enforced in the
ReAct loop, and an untrusted-content fence. The pattern lists are teaching slots
you extend per build.
"""
from __future__ import annotations

import re

from config.settings import get_settings

_JAILBREAK = re.compile(r"ignore (all|previous) instructions|developer mode", re.I)
_PII = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{16}\b")  # SSN / bare card number


def check_input(text: str) -> tuple[str | None, str | None]:
    s = get_settings()
    if len(text) > s.max_input_chars:
        return "INPUT_TOO_LONG", f"input exceeds {s.max_input_chars} chars"
    if _JAILBREAK.search(text):
        return "JAILBREAK_BLOCKED", "input matched a jailbreak pattern"
    return None, None


def check_output(text: str) -> tuple[str | None, str | None]:
    if not text or not text.strip():
        return "EMPTY_OUTPUT", "model produced no output"
    if _PII.search(text):
        return "PII_DETECTED", "output appears to contain PII"
    return None, None


def budget_exceeded(state) -> tuple[str | None, str | None]:
    """Hard caps read against the SHARED `iterations` counter + cumulative cost.
    The step cap is the loop-of-death guard."""
    s = get_settings()
    if state.get("iterations", 0) >= s.react_max_steps:
        return "MAX_STEPS", f"hit react_max_steps={s.react_max_steps}"
    if state.get("cost_usd", 0.0) > s.max_cost_usd_per_run:
        return "COST_BUDGET", f"exceeded max_cost_usd_per_run={s.max_cost_usd_per_run}"
    if state.get("tokens_in", 0) + state.get("tokens_out", 0) > s.max_tokens_per_run:
        return "TOKEN_BUDGET", f"exceeded max_tokens_per_run={s.max_tokens_per_run}"
    return None, None


def wrap_untrusted(text: str) -> str:
    """Fence retrieved/tool text so it can't act as instructions (poisoning fix)."""
    return f"<untrusted_context>\n{text}\n</untrusted_context>"
