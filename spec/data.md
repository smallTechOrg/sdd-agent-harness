# Data Model

## Storage Technology

SQLite via SQLAlchemy (sync) at `data/agent.db`. Single-user local tool; SQLite is the user-specified choice. The `data/` directory is created at startup if it does not exist. The existing Alembic migration setup (`alembic/`) is used; new tables are added via migration `0002_data_analysis.py`.

---

## File Storage

Uploaded files are stored on the local filesystem. Path convention:

```
data/uploads/<uuid>.<original-extension>
```

Example: `data/uploads/f47ac10b-58cc-4372-a567-0e02b2c3d479.csv`

The `data/uploads/` directory is created at startup if it does not exist. Files are never automatically deleted. The `filepath` field in the `uploads` table stores the absolute path resolved at upload time.

---

## Entities

### Entity: uploads

Stores metadata about each uploaded file. One row per upload.

| Field | SQLite Type | Required | Description |
|-------|-------------|----------|-------------|
| id | TEXT | Yes | UUID primary key, generated at insert |
| filename | TEXT | Yes | Original filename as provided by the browser |
| filepath | TEXT | Yes | Absolute path to the saved file on disk |
| row_count | INTEGER | Yes | Number of data rows (excluding header) |
| col_count | INTEGER | Yes | Number of columns |
| columns_json | TEXT | Yes | JSON array of `{ "name": str, "dtype": str }` objects |
| uploaded_at | TIMESTAMP WITH TIME ZONE | Yes | UTC timestamp of upload |

SQLAlchemy model: `UploadRow` in `src/db/models.py`.

---

### Entity: analyses

Stores each analysis request and its result. One row per analysis run.

| Field | SQLite Type | Required | Description |
|-------|-------------|----------|-------------|
| id | TEXT | Yes | UUID primary key, generated at insert |
| upload_id | TEXT | Yes | Foreign key → uploads.id |
| analysis_type | TEXT | Yes | One of: summary_stats, trend_over_time, top_bottom_n, correlation, nl_query |
| params_json | TEXT | No | JSON object of analysis parameters; null for summary_stats and nl_query |
| question | TEXT | No | Free-text question; populated only for nl_query |
| status | TEXT | Yes | "pending", "completed", or "failed" |
| summary | TEXT | No | Plain-English result summary; null on failure |
| chart_json | TEXT | No | Plotly figure JSON string; null if no chart |
| table_json | TEXT | No | JSON array of row dicts (max 1000 rows); null if no table |
| error_message | TEXT | No | Error message; null on success |
| created_at | TIMESTAMP WITH TIME ZONE | Yes | UTC timestamp of request |
| updated_at | TIMESTAMP WITH TIME ZONE | Yes | UTC timestamp of last status update |

SQLAlchemy model: `AnalysisRow` in `src/db/models.py`.

---

### Entity: runs (existing — unchanged)

The existing boilerplate table. Kept for backwards compatibility with the existing `/runs` endpoint. Not used by the data analysis pipeline.

| Field | SQLite Type | Required | Description |
|-------|-------------|----------|-------------|
| id | TEXT | Yes | UUID primary key |
| status | TEXT | Yes | "pending", "completed", "failed" |
| input_text | TEXT | No | Input passed to the boilerplate transform_text node |
| output_text | TEXT | No | Output from the transform_text node |
| error_message | TEXT | No | Error message on failure |
| created_at | TIMESTAMP WITH TIME ZONE | Yes | UTC creation timestamp |
| updated_at | TIMESTAMP WITH TIME ZONE | Yes | UTC last-update timestamp |

SQLAlchemy model: `RunRow` in `src/db/models.py` (existing; unchanged).

---

## Relationships

- `analyses.upload_id` → `uploads.id` (many-to-one). One upload can have many analyses. The FK is not enforced at the SQLite level (SQLite FK enforcement requires `PRAGMA foreign_keys = ON`) but is enforced at the application layer: the `parse_upload` graph node looks up the upload by `upload_id` and fails if not found.
- `runs` is independent of `uploads` and `analyses`.

---

## Data Lifecycle

| Event | Effect |
|-------|--------|
| File uploaded | UploadRow inserted (status always "active" — no explicit status field) |
| Analysis started | AnalysisRow inserted with status="pending" |
| Analysis completed | AnalysisRow updated: status="completed", summary/chart_json/table_json set, updated_at refreshed |
| Analysis failed | AnalysisRow updated: status="failed", error_message set, updated_at refreshed |
| Server restart | All data persists (SQLite file at data/agent.db); uploaded files persist (data/uploads/) |
| File deletion | Not implemented. Files remain on disk indefinitely. UploadRow remains in DB. |

No archival or TTL policy. This is a local tool; the user manages disk space manually.

---

## Sensitive Data

- Uploaded file contents: stored on local disk under `data/uploads/`. Never transmitted externally. No encryption at rest (local-only tool assumption).
- Gemini API key: stored in `.env` only; never written to the database or logged. The `Settings` model reads it at startup.
- No PII in the database schema — the app stores only metadata about files and analysis results.
- The NL query `question` field may contain data-specific terms typed by the user; these are stored in the `analyses` table and sent to Gemini as part of the prompt. Users should be aware that question text (not file data) is transmitted to Gemini.

---

## Alembic Migrations

| Migration | Contents |
|-----------|---------|
| `0001_initial.py` | Creates the `runs` table (existing) |
| `0002_data_analysis.py` | Creates the `uploads` and `analyses` tables (new in Phase 1) |

Run all migrations before starting the server:
```
uv run alembic upgrade head
```
