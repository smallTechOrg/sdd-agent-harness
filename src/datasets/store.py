"""Dataset persistence: raw upload to disk + one-time Parquet conversion.

The raw upload is kept at ``data/uploads/<id>.<ext>`` (for re-profiling) and the
canonical, typed analysis copy is written once to ``data/datasets/<id>.parquet``.
Everything downstream (profiler, sandbox) reads the Parquet — never the raw file.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# Directories are gitignored (``data/`` is ignored); created on demand.
_UPLOADS_DIR = Path("data") / "uploads"
_DATASETS_DIR = Path("data") / "datasets"


def _ensure_dirs() -> None:
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _DATASETS_DIR.mkdir(parents=True, exist_ok=True)


def dataset_paths(dataset_id: str, ext: str) -> tuple[str, str]:
    """Return ``(upload_path, parquet_path)`` for a dataset id and raw extension.

    ``ext`` may be given with or without a leading dot (``csv`` or ``.csv``).
    """
    ext = ext.lower().lstrip(".")
    upload_path = str(_UPLOADS_DIR / f"{dataset_id}.{ext}")
    parquet_path = str(_DATASETS_DIR / f"{dataset_id}.parquet")
    return upload_path, parquet_path


def _read_raw(upload_path: str, ext: str) -> pd.DataFrame:
    """Parse a raw upload into a DataFrame. Raises ValueError on any parse failure."""
    ext = ext.lower().lstrip(".")
    try:
        if ext == "csv":
            return pd.read_csv(upload_path)
        if ext == "xlsx":
            # openpyxl is the engine for .xlsx
            return pd.read_excel(upload_path, engine="openpyxl")
        if ext == "xls":
            raise ValueError(
                "Legacy .xls files are not supported. Please re-save as .csv or .xlsx."
            )
        raise ValueError(
            f"Unsupported file type '.{ext}'. Please upload a .csv or .xlsx file."
        )
    except ValueError:
        raise
    except Exception as exc:  # pandas raises many parser-specific errors
        raise ValueError(
            f"Couldn't parse the uploaded file as {ext.upper()}: {exc}"
        ) from exc


def save_upload(file_bytes: bytes, filename: str, dataset_id: str) -> dict:
    """Persist a raw upload and convert it once to Parquet.

    Writes the raw bytes to ``data/uploads/<id>.<ext>``, parses them with pandas,
    and writes the typed frame to ``data/datasets/<id>.parquet``.

    Returns ``{upload_path, parquet_path, row_count, column_count}``.

    Raises ``ValueError`` on an unsupported type or a parse failure (the API maps
    this to a 422 ``PARSE_ERROR``). On parse failure the raw upload is removed so
    nothing partial is left behind.
    """
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if not ext:
        raise ValueError("Upload has no file extension; expected .csv or .xlsx.")

    _ensure_dirs()
    upload_path, parquet_path = dataset_paths(dataset_id, ext)

    with open(upload_path, "wb") as fh:
        fh.write(file_bytes)

    try:
        df = _read_raw(upload_path, ext)
    except ValueError:
        # don't leave a partial raw upload behind on a parse failure
        try:
            os.remove(upload_path)
        except OSError:
            pass
        raise

    if df.shape[1] == 0:
        try:
            os.remove(upload_path)
        except OSError:
            pass
        raise ValueError("The uploaded file has no columns.")

    # one-time conversion to the canonical typed format
    try:
        df.to_parquet(parquet_path, engine="pyarrow", index=False)
    except Exception as exc:
        try:
            os.remove(upload_path)
        except OSError:
            pass
        raise ValueError(f"Failed to convert the file for analysis: {exc}") from exc

    return {
        "upload_path": upload_path,
        "parquet_path": parquet_path,
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
    }


def load_dataframe(parquet_path: str) -> pd.DataFrame:
    """Load the FULL DataFrame from a Parquet path (no sampling)."""
    return pd.read_parquet(parquet_path, engine="pyarrow")
