"""Sandbox-security gates for the executor slice.

These run for real (a fresh child subprocess + a real parquet on disk) — they
are the privacy/isolation gates, so nothing here is mocked.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sandbox.executor import run_code, validate_code


@pytest.fixture
def tiny_parquet(tmp_path):
    """A small parquet fixture written via pandas.to_parquet."""
    df = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5],
            "g": ["a", "b", "a", "b", "a"],
        }
    )
    path = tmp_path / "tiny.parquet"
    df.to_parquet(path)
    return str(path)


@pytest.fixture
def big_parquet(tmp_path):
    """A parquet with more rows than MAX_RESULT_ROWS to exercise capping."""
    df = pd.DataFrame({"x": np.arange(1000), "g": (["a", "b"] * 500)})
    path = tmp_path / "big.parquet"
    df.to_parquet(path)
    return str(path)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_scalar_snippet_returns_ok_and_correct_value(tiny_parquet):
    res = run_code('result = df["x"].sum()', tiny_parquet)
    assert res["ok"] is True
    assert res["kind"] == "ok"
    assert res["error"] is None
    assert res["result"]["type"] == "scalar"
    assert res["result"]["value"] == 15


def test_dataframe_result_capped_and_shaped(big_parquet):
    # 1000-row frame → result should be capped at MAX_RESULT_ROWS (200) and
    # shaped {columns, rows}.
    res = run_code("result = df", big_parquet)
    assert res["ok"] is True
    assert res["kind"] == "ok"
    payload = res["result"]
    assert payload["type"] == "table"
    assert payload["columns"] == ["x", "g"]
    assert len(payload["rows"]) == 200  # capped at MAX_RESULT_ROWS
    assert payload["row_count"] == 1000
    assert payload["truncated"] is True


def test_series_result_shaped_as_table(tiny_parquet):
    res = run_code('result = df.groupby("g")["x"].sum()', tiny_parquet)
    assert res["ok"] is True
    payload = res["result"]
    assert payload["type"] == "table"
    # group "a" => 1+3+5 = 9, group "b" => 2+4 = 6
    rows = {r[0]: r[1] for r in payload["rows"]}
    assert rows["a"] == 9
    assert rows["b"] == 6


# ---------------------------------------------------------------------------
# Static guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\nresult = 1",
        "result = open('/etc/passwd').read()",
        "result = df.__class__",
        "result = __import__('os').listdir('.')",
        "result = eval('1+1')",
        "result = exec('x=1')",
        "from pathlib import Path\nresult = Path('.')",
    ],
)
def test_static_reject_blocks_dangerous_snippets(snippet, tiny_parquet):
    res = run_code(snippet, tiny_parquet)
    assert res["ok"] is False
    assert res["kind"] == "static_reject"
    assert res["error"] is not None
    assert res["error"].startswith("static_reject:")
    # never executed → no stdout from a child
    assert res["result"] is None


def test_validate_code_returns_none_for_clean_snippet():
    assert validate_code('result = df["x"].mean()') is None


def test_validate_code_names_offending_token():
    msg = validate_code("import os\nresult = 1")
    assert msg is not None
    assert msg.startswith("static_reject:")
    assert "import" in msg


# ---------------------------------------------------------------------------
# Network blocked (privacy/sandbox gate)
# ---------------------------------------------------------------------------


def test_network_access_does_not_succeed(tiny_parquet):
    # `import socket` is caught by the static guard; assert it does NOT succeed.
    res = run_code(
        "import socket\n"
        "s = socket.socket()\n"
        "s.connect(('1.1.1.1', 80))\n"
        "result = 'leaked'",
        tiny_parquet,
    )
    assert res["ok"] is False
    assert res["result"] != {"type": "scalar", "value": "leaked"}
    # static guard catches `import`/`socket` before any execution
    assert res["kind"] == "static_reject"


def test_socket_guard_blocks_in_child_when_guard_bypassed(tiny_parquet, monkeypatch):
    """Belt-and-braces: even if the static guard were bypassed, the in-child
    socket guard must fail closed. We exercise the child guard directly by
    importing the harness's guard installer and confirming socket creation
    raises after it runs."""
    import importlib

    runner_child = importlib.import_module("sandbox.runner_child")
    import socket as _socket

    original = _socket.socket
    try:
        runner_child._install_socket_guard()
        with pytest.raises(OSError):
            _socket.socket()
    finally:
        _socket.socket = original


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_infinite_loop_times_out(tiny_parquet, monkeypatch):
    # Shrink the timeout so the test is fast.
    monkeypatch.setenv("AGENT_SANDBOX_TIMEOUT_SECONDS", "2")
    res = run_code("while True:\n    pass\nresult = 1", tiny_parquet)
    assert res["ok"] is False
    assert res["kind"] == "timeout"
    assert res["error"] is not None
    assert "time limit" in res["error"].lower()


# ---------------------------------------------------------------------------
# Runtime error
# ---------------------------------------------------------------------------


def test_runtime_error_surfaces_as_runtime_error(tiny_parquet):
    res = run_code('result = df["does_not_exist"].sum()', tiny_parquet)
    assert res["ok"] is False
    assert res["kind"] == "runtime_error"
    assert res["error"] is not None


def test_missing_result_variable_is_runtime_error(tiny_parquet):
    res = run_code("total = df['x'].sum()", tiny_parquet)
    assert res["ok"] is False
    assert res["kind"] == "runtime_error"
    assert "result" in res["error"].lower()


# ---------------------------------------------------------------------------
# Isolation: AGENT_* secrets are stripped from the child env
# ---------------------------------------------------------------------------


def test_agent_env_is_not_visible_to_child(tiny_parquet, monkeypatch):
    monkeypatch.setenv("AGENT_GEMINI_API_KEY", "super-secret-sentinel")
    # The child cannot `import os`, so it cannot read env directly via generated
    # code anyway; this asserts the executor scrubs AGENT_* from the child env.
    from sandbox.executor import _child_env

    env = _child_env()
    assert "AGENT_GEMINI_API_KEY" not in env
    # PYTHONPATH must include src/ so the child can import sandbox.runner_child.
    assert "PYTHONPATH" in env
    assert any(p.endswith("/src") for p in env["PYTHONPATH"].split(":"))
