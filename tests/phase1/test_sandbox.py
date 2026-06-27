import pandas as pd
import pytest

from execution.sandbox import SandboxError, run_code


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": ["Alice", "Bob", "Carol"],
            "salary": [100, 200, 300],
        }
    )


def test_runs_safe_pandas_and_returns_result(df):
    code = "result = df['salary'].mean()"
    result_repr, steps = run_code(code, df)
    assert result_repr == "200.0"


def test_captures_stdout_as_steps(df):
    code = "print('computing mean')\nresult = df['salary'].mean()\nprint('done', result)"
    result_repr, steps = run_code(code, df)
    assert "computing mean" in steps
    assert "done 200.0" in steps
    assert result_repr == "200.0"


def test_result_can_be_a_dataframe(df):
    code = "result = df.groupby('name')['salary'].sum()"
    result_repr, steps = run_code(code, df)
    assert "Alice" in result_repr
    assert "100" in result_repr


def test_blocks_import_os(df):
    code = "import os\nresult = os.getcwd()"
    with pytest.raises(SandboxError):
        run_code(code, df)


def test_blocks_open(df):
    code = "result = open('/etc/passwd').read()"
    with pytest.raises(SandboxError):
        run_code(code, df)


def test_blocks_dunder_import(df):
    code = "result = __import__('os').getcwd()"
    with pytest.raises(SandboxError):
        run_code(code, df)


def test_times_out_on_infinite_loop(df):
    code = "x = 0\nwhile True:\n    x += 1\nresult = x"
    with pytest.raises(SandboxError) as exc:
        run_code(code, df, timeout=1.0)
    assert "time limit" in str(exc.value).lower()


def test_empty_code_raises(df):
    with pytest.raises(SandboxError):
        run_code("   ", df)


def test_runtime_error_surfaces_clean_message(df):
    code = "result = df['nonexistent_column'].mean()"
    with pytest.raises(SandboxError) as exc:
        run_code(code, df)
    # Clean "Type: message" string, not a raw multi-line traceback.
    assert "\n" not in str(exc.value)
    assert "nonexistent_column" in str(exc.value) or "KeyError" in str(exc.value)
