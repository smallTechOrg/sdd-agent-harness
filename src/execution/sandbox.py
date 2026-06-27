"""Practical (not hardened) sandbox for LLM-generated pandas code.

Runs a code string against a provided dataframe with a restricted set of
builtins (no ``open``, ``__import__``, ``eval``, ``exec`` of arbitrary modules,
``os``, ``subprocess``, ``socket``), a namespace exposing only ``df`` and ``pd``,
a wall-clock timeout, and captured stdout as the intermediate "steps".

See ``spec/architecture.md`` ("Code Execution Safety") for the honest risk
note: this blocks the obvious escapes for a buggy/overreaching LLM, but is not
a security boundary against an adversarial code string.
"""

import builtins
import io
import threading
from contextlib import redirect_stdout

import pandas as pd

from observability.events import get_logger

log = get_logger("execution.sandbox")

DEFAULT_TIMEOUT_SECONDS = 15.0

# Builtins we deliberately withhold from generated code.
_BLOCKED_BUILTINS = frozenset(
    {
        "open",
        "__import__",
        "eval",
        "exec",
        "compile",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "globals",
        "vars",
        "memoryview",
    }
)

# The variable the LLM is instructed to assign its final answer to.
_RESULT_VARS = ("result", "answer", "output")


class SandboxError(Exception):
    """Raised when generated code fails to execute cleanly inside the sandbox."""


def _safe_builtins() -> dict:
    safe: dict = {}
    for name in dir(builtins):
        if name.startswith("__"):
            continue
        if name in _BLOCKED_BUILTINS:
            continue
        safe[name] = getattr(builtins, name)
    return safe


def _pick_result(namespace: dict):
    for var in _RESULT_VARS:
        if var in namespace and not callable(namespace[var]):
            return namespace[var]
    # Fall back to the last non-callable, non-private user-defined binding.
    for key in reversed(list(namespace)):
        if key in ("df", "pd") or key.startswith("_"):
            continue
        value = namespace[key]
        if not callable(value):
            return value
    return None


def run_code(code: str, df: pd.DataFrame, *, timeout: float = DEFAULT_TIMEOUT_SECONDS):
    """Execute ``code`` against ``df`` and return ``(result_repr, captured_stdout)``.

    ``df`` and ``pd`` are exposed in the namespace; builtins are restricted.
    Raises ``SandboxError`` on any failure (including timeout) with a clean,
    user-safe message — never leaks a half-formed traceback as a result value.
    """
    if not code or not code.strip():
        raise SandboxError("No code to execute (empty code block).")

    safe_globals = {
        "__builtins__": _safe_builtins(),
        "pd": pd,
        "df": df,
    }

    captured = io.StringIO()
    box: dict = {}

    def _target() -> None:
        try:
            with redirect_stdout(captured):
                exec(code, safe_globals)  # noqa: S102 — practical sandbox, see module docstring
            box["result"] = _pick_result(safe_globals)
        except Exception as exc:  # noqa: BLE001 — surfaced to the LLM for self-correction
            box["error"] = f"{type(exc).__name__}: {exc}"

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout)

    stdout_text = captured.getvalue()

    if worker.is_alive():
        log.warning("sandbox.timeout", timeout=timeout)
        raise SandboxError(
            f"Code execution exceeded the {timeout:g}s time limit and was stopped."
        )

    if "error" in box:
        log.info("sandbox.execution_error", error=box["error"])
        raise SandboxError(box["error"])

    result = box.get("result")
    result_repr = "" if result is None else _stringify(result)
    log.info(
        "sandbox.executed",
        result_chars=len(result_repr),
        stdout_chars=len(stdout_text),
    )
    return result_repr, stdout_text


def _stringify(value) -> str:
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return value.to_string()
    return str(value)
