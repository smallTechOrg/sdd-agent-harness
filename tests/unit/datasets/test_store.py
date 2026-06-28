import uuid

import pandas as pd
import pytest

from datasets.store import dataset_paths, load_dataframe, save_upload


def _csv_bytes() -> bytes:
    return (
        b"region,amount,date\n"
        b"North,10,2024-01-01\n"
        b"South,20,2024-01-02\n"
        b"East,30,2024-01-03\n"
    )


def test_save_upload_roundtrip_csv():
    ds_id = uuid.uuid4().hex
    meta = save_upload(_csv_bytes(), "sales.csv", ds_id)

    assert meta["row_count"] == 3
    assert meta["column_count"] == 3
    assert meta["upload_path"].endswith(f"{ds_id}.csv")
    assert meta["parquet_path"].endswith(f"{ds_id}.parquet")

    df = load_dataframe(meta["parquet_path"])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["region", "amount", "date"]
    assert len(df) == 3
    assert set(df["region"]) == {"North", "South", "East"}


def test_dataset_paths_normalises_extension():
    ds_id = "abc123"
    upload, parquet = dataset_paths(ds_id, ".CSV")
    assert upload.endswith("abc123.csv")
    assert parquet.endswith("abc123.parquet")


def test_xls_is_out_of_scope():
    with pytest.raises(ValueError) as exc:
        save_upload(b"\xd0\xcf\x11\xe0fake-xls", "legacy.xls", uuid.uuid4().hex)
    assert ".xls" in str(exc.value).lower() or "xls" in str(exc.value).lower()


def test_unsupported_extension_raises():
    with pytest.raises(ValueError):
        save_upload(b"some text", "notes.txt", uuid.uuid4().hex)


def test_malformed_csv_raises_value_error():
    # Bytes that cannot be parsed as a tabular CSV (binary garbage with NUL bytes).
    bad = b"\x00\x01\x02\xff\xfe" * 50
    with pytest.raises(ValueError):
        save_upload(bad, "broken.csv", uuid.uuid4().hex)
