"""Seed a small demo dataset so the demo gate's real run has data to query.

`python -m src.seed` → creates a "Demo Sales" dataset, ingests sales.csv, prints the dataset id.
Idempotent enough for the gate: each call creates a fresh dataset; run_agent defaults to the latest.
"""
import asyncio
import os
import tempfile

from . import duck
from .db import get_sessionmaker, init_db
from .domain import DataTable, Dataset

DEMO_CSV = """date,region,category,amount
2026-01-05,West,Electronics,1200
2026-01-08,East,Furniture,300
2026-02-02,West,Electronics,800
2026-02-15,East,Office,150
2026-03-10,North,Furniture,250
2026-03-22,South,Electronics,600
2026-04-01,West,Office,90
2026-04-18,East,Electronics,400
2026-05-03,North,Office,210
2026-05-20,South,Furniture,500
"""


async def seed() -> str:
    await init_db()
    async with get_sessionmaker()() as s:
        ds = Dataset(name="Demo Sales")
        s.add(ds)
        await s.commit()
        ds_id = ds.id

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w")
    tmp.write(DEMO_CSV)
    tmp.close()
    try:
        meta = duck.ingest_file(ds_id, "sales", tmp.name, "sales.csv")
    finally:
        os.unlink(tmp.name)

    async with get_sessionmaker()() as s:
        s.add(DataTable(dataset_id=ds_id, table_name=meta["table_name"], filename=meta["filename"],
                        n_rows=meta["n_rows"], n_cols=meta["n_cols"], columns=meta["columns"]))
        await s.commit()
    return ds_id


if __name__ == "__main__":
    print(asyncio.run(seed()))
