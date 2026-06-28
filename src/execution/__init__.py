"""Local data-execution engine — the privacy-critical sandbox.

The full dataset is processed LOCALLY in this package and never leaves the
process. `profile` produces the bounded schema/sample/profile that may be sent
to the LLM; `sandbox` runs LLM-generated pandas code against the full
dataframe in a restricted, in-process namespace.
"""

from execution.profile import load_csv, profile_csv, profile_dataframe
from execution.sandbox import ExecResult, execute_pandas

__all__ = [
    "load_csv",
    "profile_csv",
    "profile_dataframe",
    "ExecResult",
    "execute_pandas",
]
