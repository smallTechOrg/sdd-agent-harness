# API

## API Style

REST (FastAPI) + server-rendered HTML (Jinja2) for the browser UI, **plus** an MCP **JSON-RPC 2.0**
endpoint (`POST /database/{id}`) implementing the MCP 2025-06-18 tools/resources/prompts protocol.

The three primary entities each own an `api/` module: `mcpserver.py`, `sessions.py`, `queries.py`
(`home.py` + `health.py` are support routes).

## Endpoints

### `GET /`

**Purpose:** Renders the **single-page shell** (`index.html`) on the **Analyse** tab with no active
entity — the MCP-servers list, the upload card, the sessions sidebar, and the token-usage widget.
`/`, `GET /sessions/{id}` and `GET /database/{id}` all render this same shell with different initial
state (see 06-ui).
**Response:** HTML

---

### `POST /database/upload`  (auxiliary)

**Purpose:** Convert a CSV to Parquet under a named database directory and return its data URI. Creates the
directory if absent. **Creates no entity** — it is the file-staging step the UI calls before
`POST /database` (new database) or before `POST /database/{id}/sync` (adding a table to an existing one).

**Request:** `multipart/form-data` — `database_name` (required), `file` (CSV/XLSX/JSON, required)
**Response:** JSON `{"uri": "parquet:///{name}", "table": "<table_name>"}`

| Status | Condition |
|--------|-----------|
| 400 | Missing `database_name` or `file`; unsupported type; parse/convert failed |
| 500 | Disk write failed |

---

### `POST /database`

**Purpose:** Create a database from a URI + type. Enforces **1:1 dataset↔database** (rejects a duplicate
`uri` or `name`), runs **`connection_check()` via the connector before commit** (a broken database is
never persisted), inserts the `Database` row (version 1), then runs the **sync pipeline** — which inspects
the tables and generates its tools/resources/prompts (no physical-table catalog is stored).

- **Internal (parquet, default):** `database_uri = parquet:///{name}` (canonical, derived from the name;
  a file is staged via a prior `/upload`, but a database with zero tables is valid).
- **External (`postgresql` / `sqlite` / `mongodb` / `snowflake`):** `database_uri` is the connection URI
  (always enabled — no feature flag).

**Request:** `application/x-www-form-urlencoded` or JSON — `database_uri` (required for external),
`database_type` (`parquet` default | `postgresql` | `sqlite` | `mongodb` | `snowflake`), `name` (optional;
defaults to the URI's database name)
**Response:** Redirect to `GET /` (form) or JSON `{database}` (API)

| Status | Condition |
|--------|-----------|
| 400 | Missing/duplicate `name`/`uri`; unknown `database_type`; missing external URI; `connection_check()` failed (credential-free message) |
| 500 | Unexpected error |

---

### `POST /database/{id}/sync`

**Purpose:** Re-run the 5-stage LLM sync pipeline against the dataset and the **existing** capabilities,
then **transactionally apply** the result: match→update, new→insert, missing→**soft-delete** (never hard
delete); bump `version`; set title/description/`last_synced_at`/`last_sync_status` (the schema lives on the `kind='schema'` resource).
Closes the pools of sessions attached to this server. *(The user originally specified `GET`; this is a
mutation that bumps version, so it is `POST`.)*

**Response:** Redirect to `GET /` (form) or JSON `{server, version}` (API)

| Status | Condition |
|--------|-----------|
| 404 | Server not found |
| 400 | `connection_check()` failed (parquet file missing / external connect failed — credential-free) |

---

### `POST /database/{id}`  — MCP JSON-RPC 2.0 dispatch

**Purpose:** The standards-compliant MCP surface over the server's stored capability rows. A single
endpoint dispatching on `method`. Request: `{"jsonrpc":"2.0","id":…,"method":"…","params":{…}}`.

**Read methods (Phase A):**

| Method | Params | Result |
|--------|--------|--------|
| `tools/list` | `{cursor?}` | `{tools:[{name,title?,description,inputSchema,outputSchema?,annotations?}], nextCursor?}` |
| `tools/call` | `{name, arguments}` | `CallToolResult {content:[{type:"text",text}], structuredContent?, isError}` |
| `resources/list` | `{cursor?}` | `{resources:[{uri,name,title?,description,mimeType}], nextCursor?}` |
| `resources/read` | `{uri}` | `{contents:[{uri,mimeType,text}]}` |
| `prompts/list` | `{cursor?}` | `{prompts:[{name,title?,description,arguments}], nextCursor?}` |
| `prompts/get` | `{name, arguments?}` | `{description, messages:[…]}` |

- **`tools/call`** binds `arguments` into the tool's `sql_template` via DuckDB **parameter binding** and
  runs it through the read-only SELECT guard. Query/SQL failures → `isError:true` in the **result**
  (not a JSON-RPC error). Unknown tool `name` → JSON-RPC error `-32602`.
- **Pagination:** opaque keyset `cursor` (base64 of the last `(created_at, id)`); `nextCursor` is omitted
  on the last page; a malformed/forged cursor → `-32602`. Page size = `mcp_list_page_size` (default 50).
- **Errors:** unknown `method` → `-32601`; invalid params/cursor → `-32602`; tool-execution failures use
  `isError:true`. Capabilities are filtered to **active** rows (`deleted_at IS NULL`).

**Mutation methods (Phase B — implemented):** `tools/add`, `tools/update`, `prompts/add`,
`prompts/update`, `resources/add`, `resources/update`. Params `{"definition": <stage-shaped capability>}`;
result `{ok, version, applied:{child,op,key}, cascade:{tools,prompts}, status}`. Each applies the supplied
capability then runs an **additive** partial sync of the downstream capabilities (resource → tools then
prompts; tool → prompts; prompt → none) — additive means insert/update only, **never** soft-delete a
sibling (unlike the full `/sync`). One transaction, one version bump; `add` rejects a duplicate-active
key and `update` requires an existing one (`-32602`); `tools/add`/`update` reject a non-SELECT / multi-
statement / forbidden `execution.sql_template` or a `$param` not declared in `execution.parameters`
(`-32602`); a failed mutation persists nothing; a successful one closes attached session pools
(post-commit). `tools|prompts|resources/delete` **hard-delete** the targeted row (manual action) then run
a pruning cascade; the schema resource is undeletable. Any unknown method → `-32601`. See capability 4 for
the full contract.

---

### `GET /database/{id}`

**Purpose:** Renders the single-page shell on the **Database** tab with this server active — metadata
(title, type, credential-free URI, version, last-sync status), the schema view (physical tables + typed
columns + relationships), and the active tools/resources/prompts, with **Sync** / **+ Add table** actions.
**Response:** HTML — 404 if not found.

---

### `POST /database/{id}/delete`

**Purpose:** Delete the server (unlinking sessions, cascading capability rows) and remove the dataset
directory on disk.
**Response:** Redirect to `GET /` — 404 if not found.

---

### `POST /sessions`

**Purpose:** Create a session over one or more MCP servers.
**Request:** `application/x-www-form-urlencoded` — `name` (optional), `database_ids` (≥1 required)
**Response:** Redirect to `GET /sessions/{session_id}`

| Status | Condition |
|--------|-----------|
| 400 | No server selected |
| 404 | A referenced server not found |

---

### `GET /sessions/{session_id}`

**Purpose:** Renders the single-page shell on the **Analyse** tab with this session active — its
conversation thread (newest first), attached-server chips, and the ask form. Accepts
`?new={query_record_id}` to drive the run overlay + status polling. `Cache-Control: no-store`.
**Response:** HTML — 404 if not found.

---

### `POST /sessions/{session_id}/query`

**Purpose:** Submit an NL question. Creates the QueryRecord + AgentRun and runs the LangGraph MCP pipeline
on a background daemon thread. Redirects to `GET /sessions/{session_id}?new={query_record_id}`.
**Request:** `application/x-www-form-urlencoded` — `question`

| Status | Condition |
|--------|-----------|
| 400 | Empty question |
| 404 | Session not found |

Pipeline errors are caught on the background thread and recorded on the QueryRecord (`status="failed"`);
the failed turn renders inline (`⚠ Failed: …`) on the next render/poll — never a bare 500.

---

### `POST /sessions/{session_id}/delete`

**Purpose:** Close the session's pool, then delete the Session + its QueryRecords + AgentRuns.
**Response:** Redirect to `GET /` — 404 if not found.

---

### `GET /stats/daily`

**Purpose:** Token/cost usage for the sidebar widget — today's totals (input/output tokens, query count,
summed `estimated_cost_usd`), the most recent completed query's tokens/cost, and storage (server count,
total rows). Cost is computed server-side; the UI does no pricing.
**Response:** JSON `{"data": { model, tokens_input, tokens_output, cost_usd, query_count, last_input,
last_output, last_cost, server_count, total_rows }}`

---

### `GET /health`

**Purpose:** Health check — 200 `{"status": "ok"}`.

## Authentication

None in v0.1. Single-user local deployment.
