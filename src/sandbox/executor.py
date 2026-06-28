"""Parent-side sandbox runner.

`run_code(code, dataset_path)` runs LLM-generated pandas in a fresh, locked-down
child process (`python -m sandbox.runner_child`) and maps the outcome to a stable
`ExecResult` dict. It NEVER raises — every path returns the dict.

`validate_code(code)` is the static guard the graph's `validate_code` node reuses;
it returns a rejection string naming the offending token, or `None` when the
snippet is acceptable. `run_code` calls it first and short-circuits with
`kind="static_reject"` on rejection (the code is never executed).

The ExecResult shape (frozen for the graph-node slice):

    {
        "ok": bool,
        "result": dict | None,        # serialised result payload from the child
        "stdout": str,                # raw child stdout (for debugging/observability)
        "error": str | None,          # human-readable error, None on success
        "kind": "ok" | "static_reject" | "runtime_error" | "timeout" | "memory",
        "chart_spec": dict | None,    # optional chart spec the snippet set
    }
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Limits — read from settings when available, fall back to hardcoded defaults
# so this slice does not depend on the settings slice adding new fields.
# ---------------------------------------------------------------------------

DEFAULT_SANDBOX_TIMEOUT_SECONDS = 25
DEFAULT_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_MAX_RESULT_ROWS = 200


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _timeout_seconds() -> int:
    # Env wins (lets tests shrink the timeout fast); then settings; then default.
    env_val = os.environ.get("AGENT_SANDBOX_TIMEOUT_SECONDS")
    if env_val is not None and env_val.strip() != "":
        return _int_from_env("AGENT_SANDBOX_TIMEOUT_SECONDS", DEFAULT_SANDBOX_TIMEOUT_SECONDS)
    try:
        from config.settings import get_settings

        return int(getattr(get_settings(), "sandbox_timeout_seconds", DEFAULT_SANDBOX_TIMEOUT_SECONDS))
    except Exception:
        return DEFAULT_SANDBOX_TIMEOUT_SECONDS


def _memory_limit_bytes() -> int:
    env_val = os.environ.get("AGENT_MEMORY_LIMIT_BYTES")
    if env_val is not None and env_val.strip() != "":
        return _int_from_env("AGENT_MEMORY_LIMIT_BYTES", DEFAULT_MEMORY_LIMIT_BYTES)
    try:
        from config.settings import get_settings

        return int(getattr(get_settings(), "memory_limit_bytes", DEFAULT_MEMORY_LIMIT_BYTES))
    except Exception:
        return DEFAULT_MEMORY_LIMIT_BYTES


# ---------------------------------------------------------------------------
# Static guard
# ---------------------------------------------------------------------------

# Forbidden substrings → human-readable label. Order matters only for the message.
_FORBIDDEN_TOKENS: tuple[tuple[str, str], ...] = (
    ("__import__", "__import__"),
    ("import", "import statement"),
    ("open(", "open("),
    ("os.", "os."),
    ("subprocess", "subprocess"),
    ("socket", "socket"),
    ("eval", "eval"),
    ("exec", "exec"),
    ("Path(", "Path("),
    ("__", "dunder (__) attribute/name access"),
)


def validate_code(code: str) -> str | None:
    """Static guard reused by the graph's `validate_code` node.

    Returns a rejection message naming the offending token, or `None` if the
    snippet passes. Rejection messages have the stable prefix
    ``"static_reject: "`` followed by ``"forbidden token '<token>' ..."`` so the
    graph node can surface them verbatim and the executor can reuse the same
    string for its `error` field.
    """
    if code is None or not isinstance(code, str) or code.strip() == "":
        return "static_reject: empty code — no `result` would be produced."

    for needle, label in _FORBIDDEN_TOKENS:
        if needle in code:
            return (
                f"static_reject: forbidden token '{label}' found in generated code; "
                f"code that imports, opens files, touches the OS/network, or uses "
                f"eval/exec/dunder access is not allowed in the sandbox."
            )
    return None


# ---------------------------------------------------------------------------
# ExecResult helpers
# ---------------------------------------------------------------------------


def _result(
    *,
    ok: bool,
    kind: str,
    result: dict | None = None,
    stdout: str = "",
    error: str | None = None,
    chart_spec: dict | None = None,
) -> dict:
    return {
        "ok": ok,
        "result": result,
        "stdout": stdout,
        "error": error,
        "kind": kind,
        "chart_spec": chart_spec,
    }


def _child_env() -> dict:
    """Build the child environment: strip AGENT_* and proxy vars, ensure the
    child can import `sandbox.runner_child` via PYTHONPATH=<repo>/src."""
    env: dict[str, str] = {}
    proxy_keys = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "FTP_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "ftp_proxy",
        "no_proxy",
    }
    for key, value in os.environ.items():
        if key.startswith("AGENT_"):
            continue
        if key in proxy_keys:
            continue
        env[key] = value

    # The child is launched as `python -m sandbox.runner_child`; with bare
    # imports (`pythonpath = ["src"]`) it must find the `sandbox` package on
    # PYTHONPATH. `src/` is this file's parent's parent.
    src_dir = str(Path(__file__).resolve().parent.parent)
    existing = env.get("PYTHONPATH", "")
    parts = [src_dir] + ([existing] if existing else [])
    env["PYTHONPATH"] = os.pathsep.join(parts)

    # Pass the resolved limits through to the child explicitly so it does not
    # depend on the settings slice either.
    env["AGENT_MEMORY_LIMIT_BYTES"] = str(_memory_limit_bytes())
    env["AGENT_MAX_RESULT_ROWS"] = str(
        _int_from_env("AGENT_MAX_RESULT_ROWS", DEFAULT_MAX_RESULT_ROWS)
    )
    return env


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_code(code: str, dataset_path: str) -> dict:
    """Run validated pandas in a locked-down child process. Never raises."""
    reject = validate_code(code)
    if reject is not None:
        return _result(ok=False, kind="static_reject", error=reject)

    timeout = _timeout_seconds()
    env = _child_env()

    run_dir = tempfile.mkdtemp(prefix="sandbox_run_")
    code_path = os.path.join(run_dir, "snippet.py")
    try:
        with open(code_path, "w", encoding="utf-8") as fh:
            fh.write(code)

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "sandbox.runner_child", dataset_path, code_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=run_dir,
                env=env,
                # explicit: no shell, no inherited stdin
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            return _result(
                ok=False,
                kind="timeout",
                stdout=partial,
                error=f"Code execution exceeded the {timeout}s time limit and was terminated.",
            )

        return _interpret(proc)
    except Exception as exc:  # noqa: BLE001 — never let run_code raise
        return _result(
            ok=False,
            kind="runtime_error",
            error=f"Sandbox failed to launch: {type(exc).__name__}: {exc}",
        )
    finally:
        # Best-effort cleanup of the per-run temp dir.
        import shutil

        shutil.rmtree(run_dir, ignore_errors=True)


def _interpret(proc: subprocess.CompletedProcess) -> dict:
    """Map a completed child process to an ExecResult."""
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    payload = _last_json_blob(stdout)
    if payload is None:
        payload = _last_json_blob(stderr)

    if proc.returncode == 0 and payload is not None and payload.get("ok"):
        return _result(
            ok=True,
            kind="ok",
            result=payload.get("result"),
            stdout=stdout,
            chart_spec=payload.get("chart_spec"),
        )

    # Failure path — derive the kind from the child's reported kind, else infer.
    kind = "runtime_error"
    error = None
    if payload is not None:
        kind = payload.get("kind") or "runtime_error"
        error = payload.get("error")

    if error is None:
        combined = (stderr or "") + "\n" + (stdout or "")
        if "MemoryError" in combined or "memory" in combined.lower():
            kind = "memory"
        error = (stderr.strip() or stdout.strip() or "Code execution failed with no output.")

    if kind not in ("static_reject", "runtime_error", "timeout", "memory"):
        kind = "runtime_error"

    return _result(ok=False, kind=kind, stdout=stdout, error=error)


def _last_json_blob(text: str) -> dict | None:
    """Return the last line that parses as a JSON object, or None.

    The child prints a single JSON blob; scanning lines from the end tolerates
    any stray prints that may precede it.
    """
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None
