"""Sandboxed code execution for Pandora.

Generated pandas code is run in a locked-down subprocess (`runner_child`),
never via in-process `exec`. The parent-side entry point is `run_code`; the
same static guard (`validate_code`) is exposed for the graph's `validate_code`
node to reuse before invoking the executor.
"""

from sandbox.executor import run_code, validate_code

__all__ = ["run_code", "validate_code"]
