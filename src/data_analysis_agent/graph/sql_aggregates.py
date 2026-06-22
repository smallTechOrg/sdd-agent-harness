from __future__ import annotations

import math
import sqlite3


class SampleVariance:
    """SQLite aggregate computing sample variance (ddof=1, like Excel VAR / pandas)."""

    is_stddev = False

    def __init__(self) -> None:
        """Initialise an empty accumulator for the aggregate."""
        self._values: list[float] = []

    def step(self, value) -> None:
        """Accumulate one non-null, numeric-coercible value; ignore the rest."""
        if value is None:
            return
        try:
            self._values.append(float(value))
        except (TypeError, ValueError):
            pass

    def finalize(self) -> float:
        """Return the sample variance, or its square root for the stddev subclass."""
        n = len(self._values)
        if n < 2:
            return 0.0
        mean = sum(self._values) / n
        variance = sum((x - mean) ** 2 for x in self._values) / (n - 1)
        return math.sqrt(variance) if self.is_stddev else variance


class SampleStddev(SampleVariance):
    """SQLite aggregate computing sample standard deviation (sqrt of variance)."""

    is_stddev = True


def register_sql_functions(conn: sqlite3.Connection) -> None:
    """Register STDDEV/VARIANCE aggregate aliases that SQLite lacks by default.

    Args:
        conn: The in-memory SQLite connection to extend with the aggregates.
    """
    for name in ("STDDEV", "STDEV", "STDDEV_SAMP"):
        conn.create_aggregate(name, 1, SampleStddev)
    for name in ("VARIANCE", "VAR", "VAR_SAMP"):
        conn.create_aggregate(name, 1, SampleVariance)
