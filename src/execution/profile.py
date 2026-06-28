"""Local dataset profiling — pure pandas, NO LLM call.

Produces the bounded profile dict that the API returns and that the agent's
``build_llm_context`` is allowed to send to the model: column names + dtypes,
per-column ranges / missing / distinct, and at most ``sample_rows`` sample
rows. The full dataset is never serialized here — only the schema, profile,
and the capped sample. This is the LLM-facing side of the privacy boundary.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

# Default sample-row cap (the privacy bound). The caller normally passes the
# configured AGENT_SAMPLE_ROWS; this is the fallback when omitted.
DEFAULT_SAMPLE_ROWS = 20

# How many distinct example values to surface for an object/categorical column.
_SAMPLE_VALUES_CAP = 5


class MalformedCSVError(ValueError):
    """Raised when a CSV cannot be parsed by pandas.

    Carries the real underlying parse error message so the API layer can map
    it to a ``MALFORMED_FILE`` (400) response without losing detail.
    """


def load_csv(file_path: str) -> pd.DataFrame:
    """Load a CSV from disk into a DataFrame.

    Used by both profiling and execution so they read the file identically.
    Raises :class:`MalformedCSVError` (with the real parse error) on any file
    pandas cannot parse, so the caller can surface ``MALFORMED_FILE``.
    """
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        # A missing file is a different class of error — let it propagate.
        raise
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError, UnicodeDecodeError) as exc:
        raise MalformedCSVError(str(exc)) from exc
    return df


def _to_py(value: Any) -> Any:
    """Convert a numpy/pandas scalar into a JSON-serializable Python value.

    numpy scalars -> Python int/float/bool/str; NaN/NaT/None -> ``None``;
    pandas Timestamp -> ISO string. Everything else is returned via ``str``
    as a last resort so the output is always JSON-serializable.
    """
    if value is None:
        return None
    # pandas / numpy "missing" sentinels.
    try:
        if value is pd.NaT or (np.isscalar(value) and pd.isna(value)):
            return None
    except (TypeError, ValueError):
        # pd.isna over a non-scalar can raise; treat as present.
        pass

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return [_to_py(v) for v in value.tolist()]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (int, bool, str)):
        return value
    # Fallback: stringify anything exotic so JSON never blows up.
    return str(value)


def _profile_column(name: str, series: pd.Series) -> dict[str, Any]:
    """Build the per-column profile entry.

    Numeric columns get ``min``/``max``/``mean``; object/categorical columns
    get ``distinct`` + a few ``sample_values``. Every column carries ``name``,
    ``dtype`` and ``missing``.
    """
    dtype = str(series.dtype)
    missing = int(series.isna().sum())
    entry: dict[str, Any] = {"name": name, "dtype": dtype, "missing": missing}

    is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)

    if is_numeric:
        non_null = series.dropna()
        if len(non_null) == 0:
            entry["min"] = None
            entry["max"] = None
            entry["mean"] = None
        else:
            entry["min"] = _to_py(non_null.min())
            entry["max"] = _to_py(non_null.max())
            entry["mean"] = _to_py(float(non_null.mean()))
    else:
        # Object / categorical / bool / datetime: distinct + a few examples.
        entry["distinct"] = int(series.nunique(dropna=True))
        examples = series.dropna().unique()[:_SAMPLE_VALUES_CAP]
        entry["sample_values"] = [_to_py(v) for v in examples]

    return entry


def profile_dataframe(df: pd.DataFrame, sample_rows: int = DEFAULT_SAMPLE_ROWS) -> dict[str, Any]:
    """Profile an in-memory DataFrame into the API's profile shape.

    Returns::

        {
          "row_count": int,
          "columns": [ {name, dtype, missing, ...}, ... ],
          "sample_rows": [ {col: value, ...}, ... ]   # <= sample_rows rows
        }

    All values are JSON-serializable (numpy scalars -> Python, NaN -> null).
    No LLM call — pure pandas. ``sample_rows`` caps the number of sample rows
    surfaced (the privacy bound): the slice never exceeds this many rows,
    regardless of how large the full file is.
    """
    cap = max(0, int(sample_rows))

    columns = [_profile_column(name, df[name]) for name in df.columns]

    sample_df = df.head(cap)
    sample_records: list[dict[str, Any]] = []
    for _, row in sample_df.iterrows():
        sample_records.append({col: _to_py(row[col]) for col in df.columns})

    return {
        "row_count": int(len(df)),
        "columns": columns,
        "sample_rows": sample_records,
    }


def profile_csv(file_path: str, sample_rows: int = DEFAULT_SAMPLE_ROWS) -> dict[str, Any]:
    """Load a CSV from ``file_path`` and profile it.

    Thin wrapper over :func:`load_csv` + :func:`profile_dataframe`. Raises
    :class:`MalformedCSVError` on an unparseable file.
    """
    df = load_csv(file_path)
    return profile_dataframe(df, sample_rows=sample_rows)
