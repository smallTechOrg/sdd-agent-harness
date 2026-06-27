"""Schema inference for uploaded CSV/Excel files.

`infer(file_path)` reads a file locally (pandas) and returns an LLM-safe schema
description: column names + a coarse dtype in {"string", "number", "date"} plus
the row count. It NEVER returns raw rows.
"""
from __future__ import annotations

import os

import pandas as pd
from pandas.api import types as ptypes

# Coarse dtypes exposed to the rest of the system / the LLM.
DTYPE_STRING = "string"
DTYPE_NUMBER = "number"
DTYPE_DATE = "date"

_CSV_EXTS = {".csv"}
_XLSX_EXTS = {".xlsx"}


def _ext(file_path: str) -> str:
    return os.path.splitext(file_path)[1].lower()


def load_dataframe(file_path: str) -> pd.DataFrame:
    """Load a CSV/.xlsx file into a DataFrame.

    Raises ValueError on unsupported extension, missing file, or empty/unreadable
    content. Shared by schema inference and aggregation so both read identically.
    """
    if not file_path or not os.path.isfile(file_path):
        raise ValueError(f"File not found: {file_path!r}")

    ext = _ext(file_path)
    try:
        if ext in _CSV_EXTS:
            df = pd.read_csv(file_path)
        elif ext in _XLSX_EXTS:
            # First sheet, header in row 1.
            df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
        else:
            raise ValueError(
                f"Unsupported file type {ext!r}; expected one of: .csv, .xlsx"
            )
    except ValueError:
        raise
    except Exception as exc:  # pragma: no cover - defensive: corrupt file
        raise ValueError(f"Could not read file {os.path.basename(file_path)}: {exc}")

    if df.shape[1] == 0:
        raise ValueError("File has no columns")
    if len(df) == 0:
        raise ValueError("File has no data rows")
    return df


def _looks_like_dates(series: pd.Series) -> bool:
    """Best-effort: does an object column parse cleanly as dates?"""
    sample = series.dropna()
    if sample.empty:
        return False
    # Only attempt on strings — avoid coercing pure numbers into dates.
    if not all(isinstance(v, str) for v in sample.head(50)):
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    # Require the vast majority to parse, and at least one separator-ish token,
    # to avoid treating plain words as dates.
    ok_ratio = parsed.notna().mean()
    return bool(ok_ratio >= 0.9)


def _coarse_dtype(series: pd.Series) -> str:
    if ptypes.is_datetime64_any_dtype(series):
        return DTYPE_DATE
    if ptypes.is_bool_dtype(series):
        return DTYPE_STRING
    if ptypes.is_numeric_dtype(series):
        return DTYPE_NUMBER
    if _looks_like_dates(series):
        return DTYPE_DATE
    return DTYPE_STRING


def infer(file_path: str) -> dict:
    """Infer the schema of a CSV/.xlsx file.

    Returns exactly:
        {"columns": [{"name": str, "dtype": "string"|"number"|"date"}, ...],
         "row_count": int}

    Raises ValueError on unsupported/empty/unreadable files. No raw rows are
    returned.
    """
    df = load_dataframe(file_path)
    columns = [
        {"name": str(col), "dtype": _coarse_dtype(df[col])}
        for col in df.columns
    ]
    return {"columns": columns, "row_count": int(len(df))}
