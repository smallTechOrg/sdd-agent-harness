from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import pandas as pd


@dataclass
class IngestResult:
    parquet_path: str
    column_names: list[str]
    schema_json: str    # JSON: [{"name": str, "dtype": str, "nullable": bool}]
    row_count: int
    file_size_bytes: int


class FileIngester:
    """
    Converts an uploaded data file to Parquet and extracts schema metadata.

    Supported source formats: .csv  (future: .xlsx, .xls, .json)

    Single public method:
        ingest(source_path, dest_dir, stem) -> IngestResult

    The Parquet file is written to dest_dir/<stem>.parquet using Snappy
    compression. `stem` should be the DataSource UUID to guarantee
    filename uniqueness while remaining cross-referenceable to the DB.
    """

    _READERS: dict[str, object] = {
        ".csv":  lambda p: pd.read_csv(p),
        ".xlsx": lambda p: pd.read_excel(p),
        ".xls":  lambda p: pd.read_excel(p),
        ".json": lambda p: pd.read_json(p),
    }

    def ingest_stream(
        self, stream: BinaryIO, suffix: str, dest_dir: Path, stem: str
    ) -> IngestResult:
        """
        Read from an upload stream (no temp file written), convert to Parquet.
        `suffix` must include the leading dot, e.g. '.csv'.
        `stem` should be the DataSource UUID.
        """
        reader = self._READERS.get(suffix.lower())
        if reader is None:
            supported = ", ".join(self._READERS)
            raise ValueError(
                f"Unsupported file type {suffix!r}. Supported: {supported}"
            )

        raw = io.BytesIO(stream.read())
        df: pd.DataFrame = reader(raw)
        return self._write_parquet(df, dest_dir, stem)

    def ingest(self, source_path: str, dest_dir: Path, stem: str) -> IngestResult:
        """Read from an existing file on disk and convert to Parquet."""
        suffix = Path(source_path).suffix.lower()
        reader = self._READERS.get(suffix)
        if reader is None:
            supported = ", ".join(self._READERS)
            raise ValueError(
                f"Unsupported file type {suffix!r}. Supported: {supported}"
            )
        df: pd.DataFrame = reader(source_path)
        return self._write_parquet(df, dest_dir, stem)

    def _write_parquet(self, df: pd.DataFrame, dest_dir: Path, stem: str) -> IngestResult:
        """Write a DataFrame to ``dest_dir/<stem>.parquet`` and return its metadata."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = dest_dir / f"{stem}.parquet"
        df.to_parquet(str(parquet_path), index=False, engine="pyarrow", compression="snappy")

        schema = [
            {
                "name": col,
                "dtype": str(df[col].dtype),
                "nullable": bool(df[col].isna().any()),
            }
            for col in df.columns
        ]

        return IngestResult(
            parquet_path=str(parquet_path),
            column_names=list(df.columns),
            schema_json=json.dumps(schema),
            row_count=len(df),
            file_size_bytes=parquet_path.stat().st_size,
        )
