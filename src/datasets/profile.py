import pandas as pd
from pandas.api.types import is_numeric_dtype

from domain.dataset import ColumnProfile, DatasetProfile, SchemaSummary
from observability.events import get_logger

log = get_logger("datasets.profile")

DEFAULT_SAMPLE_ROWS = 5


def _column_stats(series: "pd.Series") -> dict[str, str]:
    """Bounded per-column summary stats, all stringified to stay small/portable."""
    stats: dict[str, str] = {
        "non_null": str(int(series.notna().sum())),
        "null": str(int(series.isna().sum())),
        "unique": str(int(series.nunique(dropna=True))),
    }
    if is_numeric_dtype(series) and series.notna().any():
        stats["min"] = str(series.min())
        stats["max"] = str(series.max())
        stats["mean"] = str(round(float(series.mean()), 4))
    else:
        top = series.dropna().astype(str).value_counts().head(1)
        if not top.empty:
            stats["most_common"] = str(top.index[0])
    return stats


def build_profile(
    local_path: str, sample_rows: int = DEFAULT_SAMPLE_ROWS
) -> DatasetProfile:
    """Parse a local CSV into a dataframe and build a bounded schema summary.

    The returned `schema_summary` (column names + dtypes + a small capped sample +
    per-column stats) is the ONLY data later sent to the LLM, so it is kept small.
    Raises on a file pandas cannot parse — the caller records status=failed.
    """
    df = pd.read_csv(local_path)

    columns = [str(c) for c in df.columns]
    column_profiles = [
        ColumnProfile(
            name=str(col),
            dtype=str(df[col].dtype),
            stats=_column_stats(df[col]),
        )
        for col in df.columns
    ]

    capped = max(0, sample_rows)
    sample_df = df.head(capped)
    sample = [
        {str(k): "" if pd.isna(v) else str(v) for k, v in row.items()}
        for row in sample_df.to_dict(orient="records")
    ]

    schema_summary = SchemaSummary(
        columns=column_profiles,
        sample_rows=sample,
        sample_row_count=len(sample),
    )

    profile = DatasetProfile(
        row_count=int(len(df)),
        column_count=int(df.shape[1]),
        columns=columns,
        schema_summary=schema_summary,
    )

    log.info(
        "dataset.profiled",
        local_path=local_path,
        row_count=profile.row_count,
        column_count=profile.column_count,
        sample_rows=schema_summary.sample_row_count,
    )
    return profile
