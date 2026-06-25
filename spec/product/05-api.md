# API

## API Style

REST (FastAPI) + Server-rendered HTML (Jinja2). Browser UI is the primary surface.

## Endpoints

### `GET /`

**Purpose:** Datasets home page — lists all Datasets with their type, table count, credential-free URI, last sync, and session counts.

**Response:** HTML

---

### `POST /datasources/upload`

**Purpose:** Create a Dataset. A dataset is a named, URI-addressed collection of tables; the canonical tool name is the dataset name. Two modes:

- **Internal (parquet, default):** accept a CSV `file`, convert it to a Parquet file under the dataset directory, and create a `DataSource` (Dataset) row plus its first `DatasetTableRow` (one CSV → one Parquet → one table) with LLM-generated `tool_description` and a per-table `capability_description`.
- **External (database, BETA):** accept a `dataset_uri` (e.g. `postgresql://user:pass@host:port/db`) instead of a file; introspect the database into one `DatasetTableRow` per table. Gated by `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` (default off).

No tool rows are written — the dataset's MCP server (one server per dataset, one capability per table) is materialized at query time. Creation runs `connection_check()` (parquet: directory + each Parquet readable; external: a real connect + `SELECT 1` + introspection) **before commit**; a broken dataset is never persisted.

**Request:** `multipart/form-data` — fields: `dataset_name` (required), `dataset_type` (`parquet` (default) | `postgresql`), and either `file` (parquet) or `dataset_uri` (external)

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Missing/duplicate `dataset_name`; no file or no `dataset_uri` for the chosen type; unsupported file type; parse/convert failed; or `connection_check()` failed (credential-free message) |
| 501 | External `dataset_type` requested while `DATAANALYSIS_ENABLE_EXTERNAL_DATASETS` is off |
| 500 | Disk write failed |

---

### `POST /datasources/{datasource_id}/add-csv`

**Purpose:** Append a table to an existing parquet dataset. Accept a CSV `file`, derive a table name (auto-suffix `_2`, `_3` on collision within the dataset), convert it to a Parquet file under the dataset directory, and insert a new `DatasetTableRow`. Re-generates the dataset `tool_description` and per-table `capability_description`s over **all** tables. Runs `connection_check()` before commit; closes the pools of sessions attached to this dataset so the new table becomes visible.

**Request:** `multipart/form-data` with field `file`

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Dataset not found |
| 400 | No file provided, unsupported type, parse/convert failed, not a parquet dataset, or `connection_check()` failed (credential-free message) |
| 500 | Disk write failed |

---

### `POST /datasources/{datasource_id}/sync`

**Purpose:** Re-generate the dataset's `tool_description` and every per-table `capability_description` from the schema of **all** tables (e.g. after an upload-time LLM failure) and write them back, setting `last_synced_at`. Runs `connection_check()` before commit and closes the pools of sessions attached to this dataset.

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Dataset not found |
| 400 | `connection_check()` failed — parquet file missing (re-upload required) or external connect failed (credential-free message) |

---

### `GET /datasources/{datasource_id}`

**Purpose:** Show a Dataset's detail page: metadata, type, credential-free URI, its tables/schema, and list of sessions.

**Response:** HTML

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Dataset not found |

---

### `POST /datasources/{datasource_id}/delete`

**Purpose:** Delete the Dataset (unlinking it from sessions and deleting its child `DatasetTableRow`s) and remove the whole dataset directory on disk.

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Dataset not found |

---

### `POST /sessions`

**Purpose:** Create a new Session spanning one or more Datasets.

**Request:** `application/x-www-form-urlencoded` — fields: `name` (optional), `data_source_ids` (one or more values, at least one required)

**Response:** Redirect to `GET /sessions/{session_id}`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | No dataset selected |
| 404 | Any referenced Dataset not found |

---

### `GET /sessions/{session_id}`

**Purpose:** Show the session page: Dataset metadata, all past Q&A for this session (newest first), and the "Ask a question" form. Accepts `?new={query_record_id}` to highlight/scroll to a newly added answer.

**Response:** HTML

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Session not found |

---

### `POST /sessions/{session_id}/query`

**Purpose:** Submit a natural language question. Creates the QueryRecord + AgentRun and runs the LangGraph MCP pipeline on a background daemon thread (which owns its own `asyncio` loop). Redirects to `GET /sessions/{session_id}?new={query_record_id}`.

**Request:** `application/x-www-form-urlencoded` with field `question`

**Response:** Redirect on success; renders `error.html` on pipeline failure

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | Empty question |
| 404 | Session not found |
| 500 | Pipeline error — renders error.html with detail |

---

### `POST /sessions/{session_id}/delete`

**Purpose:** Delete a Session and all its QueryRecords and AgentRuns.

**Response:** Redirect to `GET /datasources/{datasource_id}`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | Session not found |

---

### `GET /health`

**Purpose:** Health check — returns 200 with `{"status": "ok"}`.

**Response:**
```json
{"status": "ok"}
```

## Authentication

None in v0.1. Single-user local deployment.
