import json as _json
import os
import subprocess
import tempfile
import time

from data_analysis.graph.state import ExecutionResult

TIMEOUT_S = 30
PREAMBLE = """import sys
import json
import warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np
try:
    import duckdb
except ImportError:
    pass
"""


def execute_python_code(
    code: str,
    data_paths: list[str],
    query_run_id: str,
    iteration: int,
) -> ExecutionResult:
    """
    Write code to a temp file and execute it in a subprocess.
    Never uses exec() or eval().
    Returns ExecutionResult with stdout, stderr, success, elapsed_s,
    complete=False (set by inspect_result node).
    """
    data_paths_str = json_safe_paths(data_paths)
    full_code = f"{PREAMBLE}\nDATA_PATHS = {data_paths_str}\n\n{code}"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix=f"da_{query_run_id[:8]}_iter{iteration}_",
        delete=False,
    ) as f:
        f.write(full_code)
        tmpfile = f.name

    start = time.time()
    try:
        result = subprocess.run(
            ["python", tmpfile],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
        elapsed = time.time() - start
        return ExecutionResult(
            stdout=result.stdout[:10000],  # cap at 10k chars
            stderr=result.stderr[:2000],
            success=result.returncode == 0,
            elapsed_s=round(elapsed, 3),
            complete=False,  # set by inspect_result node
            explanation="",
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return ExecutionResult(
            stdout="",
            stderr=f"TimeoutError: execution exceeded {TIMEOUT_S}s",
            success=False,
            elapsed_s=round(elapsed, 3),
            complete=False,
            explanation="",
        )
    finally:
        try:
            os.unlink(tmpfile)
        except Exception:
            pass


def json_safe_paths(paths: list[str]) -> str:
    return _json.dumps(paths)
