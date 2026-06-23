# API

## API Style

REST (FastAPI) + Server-rendered HTML (Jinja2). Browser UI is the primary surface.

## Endpoints

### `GET /`

**Purpose:** Data Sources home page — lists all DataSources with session counts and last activity.

**Response:** HTML

---

### `POST /datasources/upload`

**Purpose:** Accept a file (`.csv`/`.xlsx`/`.json`). Converts it to Parquet and creates a single `DataSource` row (with LLM-generated `tool_description`/`capability_description`) atomically. No tool rows are written — the source's MCP server is materialized at query time.

**Request:** `multipart/form-data` with field `file`

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | No file provided, unsupported type, or parse/convert failed |
| 500 | Disk write failed |

---

### `POST /datasources/{datasource_id}/sync`

**Purpose:** Re-generate the data source's `tool_description` and `capability_description` from its stored Parquet (e.g. after an upload-time LLM failure) and write them back onto the `DataSource`.

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | DataSource not found |
| 400 | Parquet file missing — re-upload required |

---

### `GET /datasources/{datasource_id}`

**Purpose:** Show a DataSource's detail page: metadata, schema, and list of sessions.

**Response:** HTML

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | DataSource not found |

---

### `POST /datasources/{datasource_id}/delete`

**Purpose:** Delete the DataSource (unlinking it from sessions) and its Parquet file on disk.

**Response:** Redirect to `GET /`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 404 | DataSource not found |

---

### `POST /sessions`

**Purpose:** Create a new Session spanning one or more DataSources.

**Request:** `application/x-www-form-urlencoded` — fields: `name` (optional), `data_source_ids` (one or more values, at least one required)

**Response:** Redirect to `GET /sessions/{session_id}`

**Error cases:**
| Status | Condition |
|--------|-----------|
| 400 | No data source selected |
| 404 | Any referenced DataSource not found |

---

### `GET /sessions/{session_id}`

**Purpose:** Show the session page: DataSource metadata, all past Q&A for this session (newest first), and the "Ask a question" form. Accepts `?new={query_record_id}` to highlight/scroll to a newly added answer.

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
