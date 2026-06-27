"""Deterministic seed for the Phase-1 sample ``sales`` dataset.

Creates the ``sales`` table in DuckDB (if absent) and inserts ~200 deterministic
rows (fixed random seed) spanning all regions, products, and several recent
months — enough variety that questions like "total sales by region", "monthly
sales trend", and "top products by revenue" all return non-trivial chartable
results.

Idempotent: re-running does not duplicate rows.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from observability.events import get_logger
from analytics.duckdb_engine import get_connection

log = get_logger("analytics.seed")

SALES_TABLE = "sales"

_REGIONS = ["North", "South", "East", "West"]
_PRODUCTS = ["Widget", "Gadget", "Gizmo", "Doohickey"]
_PRODUCT_BASE_PRICE = {
    "Widget": 9.99,
    "Gadget": 24.50,
    "Gizmo": 14.25,
    "Doohickey": 5.75,
}

_ROW_COUNT = 200
_SEED = 1337


def _generate_rows() -> list[tuple]:
    """Return ~200 deterministic sales rows."""
    rng = random.Random(_SEED)
    # Anchor to a fixed date so the seed is fully deterministic across runs.
    anchor = date(2024, 6, 30)
    span_days = 180  # ~6 recent months

    rows: list[tuple] = []
    for order_id in range(1, _ROW_COUNT + 1):
        order_date = anchor - timedelta(days=rng.randint(0, span_days))
        region = rng.choice(_REGIONS)
        product = rng.choice(_PRODUCTS)
        quantity = rng.randint(1, 20)
        unit_price = _PRODUCT_BASE_PRICE[product]
        amount = round(unit_price * quantity, 2)
        rows.append((order_id, order_date, region, product, quantity, amount))
    return rows


def seed_sales(conn=None) -> dict:
    """Idempotently create + populate the ``sales`` table.

    Returns a small summary dict ``{"created": bool, "row_count": int}``.
    Safe to call repeatedly (on startup and from tests).
    """
    if conn is None:
        conn = get_connection()

    try:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SALES_TABLE} (
                order_id   INTEGER,
                order_date DATE,
                region     VARCHAR,
                product    VARCHAR,
                quantity   INTEGER,
                amount     DOUBLE
            )
            """
        )

        existing = conn.execute(f"SELECT COUNT(*) FROM {SALES_TABLE}").fetchone()[0]
        if existing and existing > 0:
            log.info("seed_sales_skip", row_count=int(existing))
            return {"created": False, "row_count": int(existing)}

        rows = _generate_rows()
        conn.executemany(
            f"INSERT INTO {SALES_TABLE} "
            "(order_id, order_date, region, product, quantity, amount) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        log.info("seed_sales_inserted", row_count=len(rows))
        return {"created": True, "row_count": len(rows)}
    except Exception as exc:
        log.error("seed_sales_failed", error=str(exc))
        raise
