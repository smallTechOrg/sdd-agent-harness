"""Token-economy guard at the data layer — real DuckDB, no LLM key required.

These tests prove that the data store never emits more sample rows than the
configured cap, which is the data-layer half of the success-criterion "no
question ever sends more than AGENT_MAX_SAMPLE_ROWS to the LLM".
"""
import json

import pandas as pd
from sqlalchemy.orm import Session

from services import duckdb_store
from services.ingest import ingest_file


def test_get_sample_rows_never_exceeds_limit(tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    df = pd.DataFrame({"n": list(range(50)), "label": [f"x{i}" for i in range(50)]})
    table = duckdb_store.sanitize_table_name("fifty.csv")

    row_count = duckdb_store.ingest_dataframe(df, table, duckdb_path)
    assert row_count == 50

    sample = duckdb_store.get_sample_rows(table, duckdb_path, limit=5)
    assert len(sample) <= 5

    # A larger limit is still bounded by the table size, never exceeds limit.
    sample10 = duckdb_store.get_sample_rows(table, duckdb_path, limit=10)
    assert len(sample10) <= 10


def test_ingest_file_stores_capped_sample(_isolated_db, tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    rows = b"id,value\n" + b"".join(f"{i},{i*2}\n".encode() for i in range(50))
    with Session(_isolated_db) as s:
        dataset = ingest_file(
            file_bytes=rows,
            filename="metrics.csv",
            session_id=None,
            duckdb_path=duckdb_path,
            max_sample_rows=5,
            db_session=s,
        )
        s.commit()
        stored = json.loads(dataset.sample_rows_json)
        assert len(stored) <= 5
        # The full data still lives in DuckDB, untouched by the cap.
        assert dataset.row_count == 50


def test_execute_select_caps_display_rows(tmp_path):
    duckdb_path = str(tmp_path / "data.duckdb")
    df = pd.DataFrame({"n": list(range(100))})
    table = duckdb_store.sanitize_table_name("hundred.csv")
    duckdb_store.ingest_dataframe(df, table, duckdb_path)

    cols, rows, full, duration_ms = duckdb_store.execute_select(
        f'SELECT * FROM "{table}"', duckdb_path, display_limit=10
    )
    assert cols == ["n"]
    assert len(rows) == 10  # capped to display_limit
    assert full == 100  # full count still reported
    assert duration_ms >= 0
