"""Ingest service tests — real DuckDB + isolated SQLite, no LLM key required."""
import json

import pytest
from sqlalchemy.orm import Session

from db.models import DatasetRow, SessionRow
from services import duckdb_store
from services.ingest import get_or_create_default_session, ingest_file


def _csv_bytes() -> bytes:
    return (
        b"region,sales,units\n"
        b"North,100,5\n"
        b"South,200,9\n"
        b"East,150,7\n"
    )


def test_ingest_csv_creates_dataset_and_table(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    with Session(_isolated_db) as s:
        dataset = ingest_file(
            file_bytes=_csv_bytes(),
            filename="sales.csv",
            session_id=None,
            duckdb_path=duckdb_path,
            max_sample_rows=5,
            db_session=s,
        )
        s.commit()
        dataset_id = dataset.id
        table_name = dataset.duckdb_table

        # Metadata is correct.
        assert dataset.row_count == 3
        assert dataset.name == "sales"
        assert dataset.source_filename == "sales.csv"
        schema = json.loads(dataset.schema_json)
        assert {c["name"] for c in schema} == {"region", "sales", "units"}
        assert all("type" in c for c in schema)

    # Dataset persisted and linked to a default session.
    with Session(_isolated_db) as s:
        fetched = s.get(DatasetRow, dataset_id)
        assert fetched is not None
        session_row = s.get(SessionRow, fetched.session_id)
        assert session_row is not None
        assert session_row.name == "Default session"

    # The table actually exists in DuckDB with the rows.
    cols = duckdb_store.get_schema(table_name, duckdb_path)
    assert {c["name"] for c in cols} == {"region", "sales", "units"}
    _, rows, full, _ = duckdb_store.execute_select(
        f'SELECT * FROM "{table_name}"', duckdb_path, display_limit=100
    )
    assert full == 3


def test_ingest_caps_sample_rows(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    rows = b"region,sales\n" + b"".join(
        f"R{i},{i}\n".encode() for i in range(50)
    )
    with Session(_isolated_db) as s:
        dataset = ingest_file(
            file_bytes=rows,
            filename="big.csv",
            session_id=None,
            duckdb_path=duckdb_path,
            max_sample_rows=5,
            db_session=s,
        )
        s.commit()
        assert dataset.row_count == 50
        samples = json.loads(dataset.sample_rows_json)
        assert len(samples) <= 5


def test_ingest_unsupported_type_raises(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    with Session(_isolated_db) as s:
        with pytest.raises(ValueError):
            ingest_file(
                file_bytes=b"some text",
                filename="notes.txt",
                session_id=None,
                duckdb_path=duckdb_path,
                max_sample_rows=5,
                db_session=s,
            )


def test_ingest_empty_file_raises(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    with Session(_isolated_db) as s:
        with pytest.raises(ValueError):
            ingest_file(
                file_bytes=b"",
                filename="empty.csv",
                session_id=None,
                duckdb_path=duckdb_path,
                max_sample_rows=5,
                db_session=s,
            )


def test_ingest_header_only_csv_raises(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    with Session(_isolated_db) as s:
        with pytest.raises(ValueError):
            ingest_file(
                file_bytes=b"a,b,c\n",
                filename="headeronly.csv",
                session_id=None,
                duckdb_path=duckdb_path,
                max_sample_rows=5,
                db_session=s,
            )


def test_get_or_create_default_session_is_idempotent(_isolated_db):
    with Session(_isolated_db) as s:
        first = get_or_create_default_session(s)
        s.commit()
        first_id = first.id
    with Session(_isolated_db) as s:
        second = get_or_create_default_session(s)
        s.commit()
        assert second.id == first_id
