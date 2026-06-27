"""Data layer: local file storage, schema inference, and local aggregation.

This package is the *only* code that reads raw uploaded rows. Raw rows live as
files under ./data/uploads/ and never enter the database, a log line, or an LLM
prompt. Callers receive only inferred schema (column names + types + row count)
and small aggregated result tables.
"""
