import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_analysis.domain.models import ColumnProfile, FileProfile


def profile_csv(file_path: str, file_size_bytes: int) -> FileProfile:
    """
    Read the CSV at file_path and return a FileProfile.

    - column names, pandas dtype as string
    - null count per column
    - up to 3 sample values (first non-null values)
    - total row count, column count
    """
    df = pd.read_csv(file_path, low_memory=False)
    columns = []
    for col in df.columns:
        col_series = df[col]
        null_count = int(col_series.isna().sum())
        non_null = col_series.dropna()
        samples = [_json_safe(v) for v in non_null.head(3).tolist()]
        columns.append(
            ColumnProfile(
                name=col,
                dtype=str(col_series.dtype),
                null_count=null_count,
                sample_values=samples,
            )
        )
    return FileProfile(
        columns=columns,
        row_count=len(df),
        column_count=len(df.columns),
        file_size_bytes=file_size_bytes,
        profiled_at=datetime.now(timezone.utc).isoformat(),
    )


def _json_safe(v):
    """Convert numpy types and NaN to JSON-serialisable Python types."""
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v
