"""Safe in-process pandas executor — the privacy/safety boundary.

The LLM writes pandas code that assigns its answer to a conventional variable
``result``; this module runs that code locally against the FULL dataframe in a
restricted namespace (only ``pd``, ``np``, and the bound ``df`` are exposed; a
reduced ``__builtins__`` allowlist excludes ``open``/``eval``/``exec``/
``__import__``/FS/network) with a wall-clock timeout, then normalizes
``result`` into JSON-serializable ``key_numbers`` + ``result_table``.

On ANY exception in the user code the real traceback + a concise message are
captured into the :class:`ExecResult` — transparency over silent retries — and
the executor never raises. The full data stays in this process; nothing is
written to disk or sent over the network.
"""

from __future__ import annotations

import math
import threading
import traceback as _traceback
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# Cap on rows materialized into a result_table — a computed frame can be large,
# but the table we hand back to the UI / persist is bounded.
RESULT_TABLE_ROW_CAP = 200

# Promote a small result frame's cells into key_numbers when it is at most this
# many rows (so a tiny aggregate also shows up as a numbers strip).
_KEY_NUMBERS_FRAME_ROW_CAP = 1

# Safe builtins allowlist. EXCLUDES open/eval/exec/__import__/compile/input and
# anything touching the filesystem or network.
_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "int", "len", "list", "map", "max",
    "min", "print", "range", "reversed", "round", "set", "slice", "sorted",
    "str", "sum", "tuple", "zip",
    # Harmless constants / exceptions the generated code may reference.
    "True", "False", "None", "Exception", "ValueError", "KeyError",
    "TypeError", "IndexError", "ZeroDivisionError", "AttributeError",
)


@dataclass
class ExecResult:
    """Normalized outcome of executing generated pandas code.

    ``result_table`` — JSON-serializable rows/columns of a tabular result
    (``list`` of row dicts, capped at :data:`RESULT_TABLE_ROW_CAP`), else
    ``None``. ``key_numbers`` — a flat ``label -> value`` dict for scalar /
    small results, else ``None``. ``error`` — a concise error message when the
    code failed, else ``None``. ``traceback`` — the real traceback string
    (sandbox frames stripped) when the code failed, else ``None``.
    """

    result_table: list | dict | None = None
    key_numbers: dict | None = None
    error: str | None = None
    traceback: str | None = field(default=None)


def _build_safe_builtins() -> dict[str, Any]:
    """Reduce ``__builtins__`` to the safe allowlist."""
    import builtins as _builtins

    safe: dict[str, Any] = {}
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(_builtins, name):
            safe[name] = getattr(_builtins, name)
    return safe


def _to_py(value: Any) -> Any:
    """Convert a numpy/pandas scalar into a JSON-serializable Python value."""
    if value is None:
        return None
    try:
        if value is pd.NaT or (np.isscalar(value) and pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return [_to_py(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (int, bool, str)):
        return value
    return str(value)


def _normalize_result(value: Any) -> ExecResult:
    """Turn the user's ``result`` value into key_numbers + result_table.

    - scalar           -> ``key_numbers={'result': value}``
    - ``pd.Series``    -> key_numbers (label -> value) + result_table
    - ``pd.DataFrame`` -> result_table (rows), + key_numbers for tiny frames
    - list/dict/tuple  -> result_table (best-effort, JSON-serializable)
    """
    # Scalar (including numpy scalars).
    if value is None or np.isscalar(value) or isinstance(
        value, (int, float, bool, str, np.generic)
    ):
        return ExecResult(key_numbers={"result": _to_py(value)})

    if isinstance(value, pd.Series):
        labels = [_to_py(k) for k in value.index.tolist()]
        values = [_to_py(v) for v in value.tolist()]
        key_numbers = {str(k): v for k, v in zip(labels, values)}
        result_table = [
            {"key": k, "value": v} for k, v in zip(labels, values)
        ][:RESULT_TABLE_ROW_CAP]
        return ExecResult(key_numbers=key_numbers, result_table=result_table)

    if isinstance(value, pd.DataFrame):
        capped = value.head(RESULT_TABLE_ROW_CAP)
        rows: list[dict[str, Any]] = []
        for _, row in capped.iterrows():
            rows.append({str(col): _to_py(row[col]) for col in capped.columns})
        result = ExecResult(result_table=rows)
        # Promote a 1-row frame into key_numbers too (a tiny aggregate).
        if len(value) <= _KEY_NUMBERS_FRAME_ROW_CAP and len(value) >= 1:
            single = value.iloc[0]
            result.key_numbers = {
                str(col): _to_py(single[col]) for col in value.columns
            }
        return result

    if isinstance(value, dict):
        return ExecResult(key_numbers={str(k): _to_py(v) for k, v in value.items()})

    if isinstance(value, (list, tuple, set, np.ndarray)):
        items = list(value)
        # A list of dict-like rows -> a table; otherwise a single result column.
        if items and all(isinstance(i, dict) for i in items):
            rows = [{str(k): _to_py(v) for k, v in i.items()} for i in items]
            return ExecResult(result_table=rows[:RESULT_TABLE_ROW_CAP])
        return ExecResult(
            result_table=[{"result": _to_py(i)} for i in items][:RESULT_TABLE_ROW_CAP]
        )

    # Anything else: stringify into key_numbers so the result is still useful.
    return ExecResult(key_numbers={"result": _to_py(value)})


def _strip_sandbox_traceback(exc: BaseException) -> str:
    """Format the traceback with the sandbox's own frames removed.

    Keeps frames originating in the generated code (filename ``<generated>``)
    plus the exception itself, so the traceback points at the user code, not
    this executor.
    """
    tb = exc.__traceback__
    # Drop frames until we reach the generated code (or run out).
    while tb is not None and tb.tb_frame.f_code.co_filename != "<generated>":
        tb = tb.tb_next

    if tb is not None:
        lines = _traceback.format_exception(type(exc), exc, tb)
    else:
        # No generated frame survived (e.g. SyntaxError at compile) — show the
        # exception without our internal stack.
        lines = _traceback.format_exception_only(type(exc), exc)
    return "".join(lines).rstrip()


def _run_code(code: str, df: pd.DataFrame) -> ExecResult:
    """Compile + exec the generated code in the restricted namespace.

    Runs on a worker thread (see :func:`execute_pandas`). Returns a normalized
    :class:`ExecResult`; never raises for user-code errors — the traceback is
    captured into the result instead.
    """
    namespace: dict[str, Any] = {
        "__builtins__": _build_safe_builtins(),
        "pd": pd,
        "np": np,
        "df": df,
    }

    try:
        compiled = compile(code, "<generated>", "exec")
    except SyntaxError as exc:
        return ExecResult(
            error=f"SyntaxError: {exc.msg}",
            traceback=_strip_sandbox_traceback(exc),
        )

    try:
        exec(compiled, namespace)  # noqa: S102 — restricted namespace, trusted local owner
    except BaseException as exc:  # noqa: BLE001 — capture everything, surface transparently
        message = f"{type(exc).__name__}: {exc}"
        return ExecResult(error=message, traceback=_strip_sandbox_traceback(exc))

    if "result" not in namespace:
        return ExecResult(
            error="Generated code did not assign a `result` variable.",
            traceback=None,
        )

    try:
        return _normalize_result(namespace["result"])
    except Exception as exc:  # noqa: BLE001 — normalization must not crash the caller
        return ExecResult(
            error=f"Result could not be serialized: {type(exc).__name__}: {exc}",
            traceback=_strip_sandbox_traceback(exc),
        )


def execute_pandas(code: str, df: pd.DataFrame, timeout_s: int = 30) -> ExecResult:
    """Execute LLM-generated pandas ``code`` against ``df`` safely.

    The code runs in a restricted namespace (only ``pd``, ``np``, ``df`` plus a
    safe builtins allowlist) on a worker thread bounded by a ``timeout_s``
    wall-clock limit. The code must assign its answer to ``result``; the value
    is normalized into JSON-serializable ``key_numbers`` + ``result_table``.

    Never raises for user-code failures: a syntax/runtime error, a missing
    ``result``, or a timeout all return an :class:`ExecResult` with ``error``
    (and the real ``traceback`` where available). No filesystem writes, no
    network — the full data stays in-process.
    """
    # A DAEMON worker thread is used (not signal-based) because signal timeouts
    # only work on the main thread; under uvicorn this runs off the main thread.
    # The thread is a daemon so a runaway snippet (e.g. an infinite loop) that
    # cannot be force-killed never blocks join()/shutdown or process exit — we
    # simply abandon it and return a clear timeout. (A pooled, non-daemon thread
    # would otherwise hang shutdown waiting for the loop to finish.)
    outcome: dict[str, ExecResult] = {}

    def _worker() -> None:
        outcome["result"] = _run_code(code, df)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout_s)

    if thread.is_alive():
        # Abandon the orphaned daemon thread; surface a clear timeout error.
        return ExecResult(error=f"Execution exceeded {timeout_s}s", traceback=None)

    # The worker finished within the timeout. It is engineered never to raise,
    # but guard against the (impossible) empty-outcome case defensively.
    return outcome.get(
        "result",
        ExecResult(error="Execution produced no result.", traceback=None),
    )
