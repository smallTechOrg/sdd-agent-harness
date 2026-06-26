"""Direct unit tests for the local sandbox and CSV profiler — NO LLM key required.

These assert the security boundary documented in
``spec/architecture.md → Sandbox Security Model``: dangerous code is REJECTED by
static validation BEFORE execution, benign pandas runs, and the profiler caps the
LLM-visible sample at the configured cap (data-locality invariant).
"""
from pathlib import Path

import pandas as pd
import pytest

from analysis.sandbox import SandboxError, run_sandbox
from analysis.profiler import ProfileError, profile
from config.settings import get_settings

_FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def df():
    return pd.read_csv(_FIXTURES / "sales.csv")


# --- Sandbox: dangerous constructs are rejected WITHOUT executing -----------


@pytest.mark.parametrize(
    "code",
    [
        "import os\nresult = 1",
        "from os import system\nresult = 1",
        "result = df.__class__.__bases__",
        "result = open('/etc/passwd').read()",
        "result = eval('1+1')",
        "result = exec('x=1')",
        "result = __import__('os').getcwd()",
        "result = os.getcwd()",
    ],
)
def test_sandbox_rejects_dangerous_code(code, df):
    settings = get_settings()
    with pytest.raises(SandboxError):
        run_sandbox(code, df, settings)


def test_sandbox_runs_benign_aggregate(df):
    settings = get_settings()
    table, scalar, truncated = run_sandbox("result = int(df['sales'].sum())", df, settings)
    assert table is None
    assert scalar == 2020
    assert truncated is False


def test_sandbox_normalizes_dataframe_result(df):
    settings = get_settings()
    code = "result = df.groupby('region')['sales'].sum().sort_values(ascending=False).reset_index()"
    table, scalar, truncated = run_sandbox(code, df, settings)
    assert scalar is None
    assert table is not None
    assert "region" in table["columns"]
    assert "sales" in table["columns"]
    # Highest-first ordering preserved through normalization.
    region_idx = table["columns"].index("region")
    sales_idx = table["columns"].index("sales")
    ordered = [(row[region_idx], row[sales_idx]) for row in table["rows"]]
    assert ordered == [("East", 590), ("West", 530), ("North", 520), ("South", 380)]


def test_sandbox_requires_result_binding(df):
    settings = get_settings()
    with pytest.raises(SandboxError):
        run_sandbox("x = df['sales'].sum()", df, settings)


# --- Profiler: caps the LLM-visible sample (data-locality invariant) --------


def test_profiler_caps_sample_rows_for_large_csv():
    settings = get_settings()
    csv_text = (_FIXTURES / "many_rows.csv").read_text(encoding="utf-8")
    df, schema, sample_rows, row_count = profile(csv_text, settings)

    cap = min(settings.sample_rows, 20)
    # The full frame is held locally...
    assert row_count == 500
    assert len(df) == 500
    # ...but only the capped sample is ever exposed for the prompt.
    assert len(sample_rows) == cap
    assert len(sample_rows) <= 20
    assert {c["name"] for c in schema} == {"id", "value"}


def test_profiler_rejects_empty_csv():
    settings = get_settings()
    with pytest.raises(ProfileError):
        profile("   ", settings)


def test_profiler_rejects_malformed_csv():
    settings = get_settings()
    # Ragged rows (inconsistent field counts) are genuinely unparseable as a CSV.
    malformed = "a,b,c\n1,2\n3,4,5,6,7\n8"
    with pytest.raises(ProfileError):
        profile(malformed, settings)
