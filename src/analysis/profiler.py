"""Local CSV profiling.

Parses the uploaded CSV text into a pandas DataFrame and derives the minimal
context that may be sent to the LLM: the column schema (names + dtypes) and a
capped sample of rows. The full DataFrame is returned for LOCAL execution only
and must NEVER be placed into any prompt.
"""

from __future__ import annotations

import io
import math

import pandas as pd


# Hard upper bound on the sample regardless of the configured `sample_rows`.
_SAMPLE_HARD_CAP = 20


class ProfileError(ValueError):
    """Raised when the CSV cannot be profiled (empty / unparseable / over caps)."""


def _json_safe(value):
    """Convert a single cell to a JSON-serializable python-native value."""
    if value is None:
        return None
    # NaN / NaT → None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except (TypeError, ValueError):
        pass
    if pd.isna(value) is True:  # handles numpy.nan, pd.NaT, None
        return None
    # numpy scalar types expose .item()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def profile(csv_text: str, settings):
    """Profile CSV text.

    Returns ``(df, schema, sample_rows, row_count)`` where:
      - ``df`` is the full pandas DataFrame (LOCAL ONLY, never sent to the LLM),
      - ``schema`` is ``[{"name": col, "dtype": str(dtype)}, ...]``,
      - ``sample_rows`` is up to ``min(settings.sample_rows, 20)`` rows as a list
        of JSON-safe dicts,
      - ``row_count`` is ``len(df)``.

    Raises :class:`ProfileError` on empty / unparseable input or when the byte
    length or row count exceeds the configured caps.
    """
    if csv_text is None or not csv_text.strip():
        raise ProfileError("The upload is empty — please provide a CSV file with data.")

    byte_len = len(csv_text.encode("utf-8"))
    if byte_len > settings.max_upload_bytes:
        raise ProfileError(
            f"The file is too large ({byte_len:,} bytes); the limit is "
            f"{settings.max_upload_bytes:,} bytes."
        )

    try:
        df = pd.read_csv(io.StringIO(csv_text))
    except pd.errors.EmptyDataError:
        raise ProfileError("Couldn't read that as a CSV — the file contains no columns or data.")
    except pd.errors.ParserError as exc:
        raise ProfileError(f"Couldn't read that as a CSV — it is malformed: {exc}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProfileError(f"Couldn't read that as a CSV: {exc}")

    if df.shape[1] == 0:
        raise ProfileError("Couldn't read that as a CSV — no columns were detected.")

    row_count = int(len(df))
    if row_count > settings.max_rows:
        raise ProfileError(
            f"The file has {row_count:,} rows; the limit is {settings.max_rows:,} rows."
        )

    schema = [{"name": str(col), "dtype": str(dtype)} for col, dtype in df.dtypes.items()]

    n_sample = min(settings.sample_rows, _SAMPLE_HARD_CAP)
    sample_df = df.head(n_sample)
    sample_rows = [
        {str(col): _json_safe(val) for col, val in row.items()}
        for row in sample_df.to_dict(orient="records")
    ]

    return df, schema, sample_rows, row_count
