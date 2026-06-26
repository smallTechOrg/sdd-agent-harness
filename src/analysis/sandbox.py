"""Constrained local execution of LLM-generated pandas code.

The generated snippet is UNTRUSTED LLM output. It is executed locally against
the full DataFrame in a restricted namespace, as documented in
``spec/architecture.md → Sandbox Security Model``:

  * AST static validation rejects imports, dunder names, and attribute access
    into dangerous modules BEFORE anything is executed.
  * ``__builtins__`` is replaced with a small allow-list; only ``df`` and ``pd``
    are otherwise bound.
  * The snippet must assign its answer to a variable named ``result``.
  * Execution runs under a thread-based wall-clock timeout.
  * The result is normalized to a JSON-serializable scalar or ``{columns, rows}``
    table, capped at ``settings.max_result_rows``.

This is defense-in-depth for a single-user local tool, NOT a hardened
multi-tenant sandbox (see the architecture doc for the documented limits).
"""

from __future__ import annotations

import ast
import math
import threading

import pandas as pd


class SandboxError(ValueError):
    """Raised for any sandbox failure (rejection / exec error / timeout / missing result)."""


# Names that may never appear as bare identifiers in the snippet.
_FORBIDDEN_NAMES = frozenset(
    {"eval", "exec", "open", "__import__", "compile", "input", "globals", "locals", "vars", "getattr", "setattr", "delattr"}
)

# Module roots whose attribute access is forbidden.
_FORBIDDEN_ATTR_ROOTS = frozenset({"os", "sys", "subprocess", "builtins"})

# The ONLY builtins exposed inside the sandbox.
_SAFE_BUILTINS = {
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "sorted": sorted,
    "round": round,
    "abs": abs,
    "range": range,
    "list": list,
    "dict": dict,
    "set": set,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
}


def _validate(code: str) -> None:
    """AST static validation. Raises :class:`SandboxError` on any rejected construct."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"The generated code is not valid Python: {exc}")

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("The generated code is not allowed to import modules.")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SandboxError(f"The generated code uses a forbidden name: {node.id!r}.")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SandboxError("The generated code is not allowed to access dunder attributes.")
            if isinstance(node.value, ast.Name) and node.value.id in _FORBIDDEN_ATTR_ROOTS:
                raise SandboxError(
                    f"The generated code is not allowed to access {node.value.id!r}."
                )
        if isinstance(node, ast.Name) and node.id.startswith("__") and node.id.endswith("__"):
            raise SandboxError("The generated code is not allowed to use dunder names.")


def _json_safe_scalar(value):
    """Convert a scalar (incl. numpy types / NaN) to a JSON-safe python value."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    try:
        if pd.isna(value) is True:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _normalize(result, settings):
    """Normalize ``result`` into (result_table | None, result_scalar | None, truncated)."""
    cap = settings.max_result_rows

    # Series → 1- or 2-column table (preserve a meaningful index).
    if isinstance(result, pd.Series):
        result = result.reset_index()
        # reset_index on an unnamed series yields columns ["index", 0]; make them strings below.

    if isinstance(result, pd.DataFrame):
        df = result
        truncated = False
        if len(df) > cap:
            df = df.head(cap)
            truncated = True
        columns = [str(c) for c in df.columns]
        rows = [[_json_safe_scalar(v) for v in row] for row in df.itertuples(index=False, name=None)]
        return {"columns": columns, "rows": rows}, None, truncated

    # Scalar (number / str / bool / numpy scalar / None).
    scalar = _json_safe_scalar(result)
    return None, scalar, False


def run_sandbox(code: str, df: pd.DataFrame, settings):
    """Execute ``code`` against ``df`` in the restricted namespace.

    Returns ``(result_table | None, result_scalar | None, truncated)`` or raises
    :class:`SandboxError`.
    """
    _validate(code)

    namespace = {
        "__builtins__": dict(_SAFE_BUILTINS),
        "df": df,
        "pd": pd,
    }

    holder: dict = {}

    def _worker() -> None:
        try:
            exec(compile(code, "<sandbox>", "exec"), namespace, namespace)  # noqa: S102 - sandboxed
        except Exception as exc:  # noqa: BLE001 - surface any exec error as a sandbox error
            holder["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=settings.exec_timeout)

    if thread.is_alive():
        # The daemon thread is abandoned; it cannot be force-killed in CPython.
        raise SandboxError(
            f"The computation took too long (over {settings.exec_timeout}s) and was stopped."
        )

    if "error" in holder:
        raise SandboxError(f"The generated code failed to run: {holder['error']}")

    if "result" not in namespace:
        raise SandboxError(
            "The generated code did not produce a `result` value, so there is no answer to show."
        )

    return _normalize(namespace["result"], settings)
