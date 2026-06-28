"""Locked-down child harness — run as `python -m sandbox.runner_child`.

Usage (invoked only by `sandbox.executor`, never a shell):

    python -m sandbox.runner_child <dataset_parquet_path> <code_temp_file>

At startup it:
  * installs a socket guard so any network call raises immediately;
  * applies a memory cap via `resource.setrlimit(RLIMIT_AS, ...)` (POSIX);
  * loads the dataset Parquet into `df` (pandas + pyarrow);
  * `exec`s the (already statically-validated) snippet in a namespace exposing
    ONLY `df`, `pd`, `np`. The snippet assigns `result` (and optional
    `chart_spec`).

It then JSON-serialises `result` and prints a single JSON blob to stdout:
  success  → {"ok": true, "result": <payload>, "chart_spec": <dict|null>}
  failure  → {"ok": false, "kind": "...", "error": "..."}  (and exits nonzero)

This module is intentionally self-contained: the executor strips AGENT_* /
proxy env vars and sets `cwd` to a per-run temp dir before launching it.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

DEFAULT_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_MAX_RESULT_ROWS = 200


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _install_socket_guard() -> None:
    """Monkeypatch socket so any network attempt fails closed."""
    import socket

    class _BlockedSocket(socket.socket):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):  # noqa: D401
            raise OSError("Network access is disabled in the sandbox.")

    def _blocked(*args, **kwargs):
        raise OSError("Network access is disabled in the sandbox.")

    socket.socket = _BlockedSocket  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    if hasattr(socket, "create_server"):
        socket.create_server = _blocked  # type: ignore[assignment]


def _apply_memory_limit() -> None:
    """Cap address space so a runaway allocation raises MemoryError, not swap."""
    try:
        import resource

        limit = _int_env("AGENT_MEMORY_LIMIT_BYTES", DEFAULT_MEMORY_LIMIT_BYTES)
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = hard
        if hard != resource.RLIM_INFINITY:
            new_hard = min(hard, limit)
        else:
            new_hard = limit
        resource.setrlimit(resource.RLIMIT_AS, (limit, new_hard))
    except (ImportError, ValueError, OSError):
        # Non-POSIX or limit not settable — proceed; the parent timeout still
        # bounds the run. (Target is POSIX per architecture.md.)
        pass


def _emit_error(kind: str, error: str) -> None:
    sys.stdout.write(json.dumps({"ok": False, "kind": kind, "error": error}) + "\n")
    sys.stdout.flush()


def _serialise_result(result, max_rows: int):
    """Convert `result` into a JSON-safe payload.

    DataFrame → {"columns": [...], "rows": [[...], ...]} capped at max_rows.
    Series    → converted to a {columns, rows} two-column table or scalar.
    scalar    → JSON-native value.
    """
    import numpy as np
    import pandas as pd

    if isinstance(result, pd.DataFrame):
        capped = result.head(max_rows)
        columns = [str(c) for c in capped.columns]
        rows = json.loads(capped.to_json(orient="values", date_format="iso", default_handler=str))
        return {
            "type": "table",
            "columns": columns,
            "rows": rows,
            "row_count": int(len(result)),
            "truncated": bool(len(result) > max_rows),
        }

    if isinstance(result, pd.Series):
        capped = result.head(max_rows)
        index_name = capped.index.name or "index"
        value_name = capped.name if capped.name is not None else "value"
        columns = [str(index_name), str(value_name)]
        rows = [
            [_scalar(idx), _scalar(val)]
            for idx, val in zip(capped.index.tolist(), capped.tolist())
        ]
        return {
            "type": "table",
            "columns": columns,
            "rows": rows,
            "row_count": int(len(result)),
            "truncated": bool(len(result) > max_rows),
        }

    return {"type": "scalar", "value": _scalar(result)}


def _scalar(value):
    """Best-effort conversion of a single value to a JSON-native type."""
    import numpy as np
    import pandas as pd

    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return f
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if value is pd.NaT:
        return None
    try:
        # numpy scalar / 0-d array
        if hasattr(value, "item"):
            return _scalar(value.item())
    except Exception:
        pass
    return str(value)


def main(argv: list[str]) -> int:
    _install_socket_guard()
    _apply_memory_limit()

    if len(argv) < 2:
        _emit_error("runtime_error", "runner_child: expected <dataset_path> <code_file> args.")
        return 2

    dataset_path, code_path = argv[0], argv[1]
    max_rows = _int_env("AGENT_MAX_RESULT_ROWS", DEFAULT_MAX_RESULT_ROWS)

    try:
        import numpy as np
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        _emit_error("runtime_error", f"runner_child: failed to import pandas/numpy: {exc}")
        return 2

    try:
        df = pd.read_parquet(dataset_path)
    except Exception as exc:  # noqa: BLE001
        _emit_error("runtime_error", f"Failed to load dataset: {type(exc).__name__}: {exc}")
        return 2

    try:
        with open(code_path, "r", encoding="utf-8") as fh:
            code = fh.read()
    except Exception as exc:  # noqa: BLE001
        _emit_error("runtime_error", f"Failed to read code file: {exc}")
        return 2

    namespace: dict = {"df": df, "pd": pd, "np": np}
    try:
        exec(code, namespace)  # noqa: S102 — sandboxed: validated snippet, restricted ns
    except MemoryError:
        _emit_error("memory", "Code execution exceeded the memory limit (MemoryError).")
        return 3
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc(limit=4)
        _emit_error("runtime_error", f"{type(exc).__name__}: {exc}\n{tb}")
        return 1

    if "result" not in namespace:
        _emit_error("runtime_error", "Code did not assign a `result` variable.")
        return 1

    try:
        payload = _serialise_result(namespace["result"], max_rows)
    except MemoryError:
        _emit_error("memory", "Serialising the result exceeded the memory limit.")
        return 3
    except Exception as exc:  # noqa: BLE001
        _emit_error("runtime_error", f"Failed to serialise result: {type(exc).__name__}: {exc}")
        return 1

    chart_spec = namespace.get("chart_spec")
    if chart_spec is not None and not isinstance(chart_spec, dict):
        chart_spec = None

    out = {"ok": True, "result": payload, "chart_spec": chart_spec}
    try:
        blob = json.dumps(out, default=str)
    except Exception as exc:  # noqa: BLE001
        _emit_error("runtime_error", f"Result is not JSON-serialisable: {exc}")
        return 1

    sys.stdout.write(blob + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
