# Architecture

---

## System Overview

A single-origin local web application. The user interacts with a Next.js UI (served as a static export by FastAPI at `/app`). They upload a CSV and ask a question; the FastAPI backend runs a LangGraph agent that profiles the file, asks Google Gemini to translate the question into a pandas computation, executes that computation **locally** over the full DataFrame inside a constrained sandbox, and returns the answer, the plain-English explanation, the generated code, and the result table. The raw dataset stays on the machine — only the schema, a capped row sample, and the question ever reach Gemini. Runs are persisted to a local SQLite database.

## Component Map

```
[Next.js UI  /app]
      │  POST /runs  (csv_text + question, JSON)
      ▼
[FastAPI  src/api/runs.py] ──► [Runner  src/graph/runner.py] ──► [SQLite  src/db]
      │                                   │
      │                                   ▼
      │                          [LangGraph  src/graph/agent.py]
      │                                   │
      │        ┌──────────────┬───────────┼──────────────┬──────────────┐
      │        ▼              ▼           ▼               ▼              ▼
      │   profile_csv    generate_code  execute_code   explain_result  finalize
      │   (local pandas) (Gemini call)  (LOCAL sandbox) (Gemini call)   (DB write)
      │                       │              │              │
      │                       ▼              ▼              ▼
      │                  [Gemini API]   [Sandbox          [Gemini API]
      │                  schema+sample   src/analysis/
      │                  +question only  sandbox.py]
      ▼                                  full df, local only
[response: answer, explanation, generated_code, result_table]
```

Key point: **`profile_csv` and `execute_code` touch the full data and run entirely locally.** Only `generate_code` and `explain_result` call Gemini, and they receive **only** the schema, a capped sample, the question, and (for explain) the small computed result — never the full dataset.

## Layers

| Layer | Responsibility |
|-------|----------------|
| UI (`frontend/`) | CSV upload, question input, render answer + explanation + "show its work" panel + labelled stubs |
| API (`src/api/`) | `POST /runs`, `GET /runs/{id}`, `/health`; request validation; `{data}`/`{detail}` envelope |
| Orchestration (`src/graph/`) | LangGraph state machine: profile → generate → execute → explain → finalize/error |
| Analysis (`src/analysis/`) | `profiler.py` (parse CSV, build schema + capped sample), `sandbox.py` (constrained local execution of generated pandas) |
| LLM (`src/llm/`) | Gemini provider, `LLMClient().call_model(prompt, system=...)` |
| Persistence (`src/db/`) | SQLite via SQLAlchemy 2.0; one `RunRow` per analysis |

## Data Flow

1. **Trigger:** user selects a mode (Pandas or SQL), uploads a CSV, and submits a question → `POST /runs` with `{ "csv_text": "...", "question": "...", "mode": "pandas" | "sql" }` (CSV sent as text in the JSON body — see [`api.md`](api.md)).
2. **Persist + start:** `runner.run_agent(csv_text, question, mode)` creates a `RunRow` (status `pending`) and invokes the graph with the mode.
3. **`profile_csv` (local):** parse `csv_text` into a pandas DataFrame; reject if unparseable or over the row/byte cap; build a **schema** (column names + inferred dtypes) and a **capped sample** (default 15 rows, hard cap 20). The full DataFrame is held in graph state for local execution; it is NOT placed in any LLM prompt. (For SQL mode, the schema is also used to create the in-memory SQLite table.)
4. **`generate_code` (Gemini, branched on mode):** 
   - **Pandas:** send the schema + capped sample + question to Gemini with the pandas code-generation system prompt; receive a single pandas expression/snippet that assigns to `result` using the bound name `df`.
   - **SQL:** send the schema + capped sample + question to Gemini with the SQL code-generation system prompt; receive a single SQL query (SELECT statement) that will be executed against the in-memory table.
5. **`execute_code` (local, branched on mode):**
   - **Pandas:** run the generated code in `src/analysis/sandbox.py` against the **full** DataFrame `df`, with restricted builtins, no imports, a wall-clock timeout, and result-size caps. Extract `result` and normalize it to a JSON-serializable scalar or table.
   - **SQL:** load the CSV into an in-memory SQLite table, execute the generated SQL query in `src/analysis/sql_executor.py` with query validation (SELECT-only, no escapes), a wall-clock timeout, and result-size caps. Extract the result set and normalize it to a JSON-serializable `{columns, rows}` table.
6. **`explain_result` (Gemini):** send the question + the generated code (pandas or SQL) + the **small** computed result to Gemini with the explanation system prompt; receive a plain-English explanation. (Never sends the full data — only the already-computed small result.)
7. **`finalize` / `handle_error`:** write status, answer fields, generated code, mode, and result table back to the `RunRow`.
8. **Output:** the API returns `{ data: { run_id, status, mode, answer, explanation, generated_code, result_table, error } }`.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini API (`gemini-2.5-flash`) | Generate pandas code; render explanation | Network/quota/model error → `handle_error`, run status `failed`, message surfaced to UI |
| pandas (local) | Parse CSV, execute computation locally | Parse error → clear "not a valid CSV" guard; exec error → categorized sandbox error |
| SQLite (local file) | Persist runs | Write error → 500 with envelope; does not block the computation itself |

No other network calls. The dataset never leaves the process except as schema + capped sample to Gemini.

## Execution Modes: Pandas and SQL

The analyst agent supports two interchangeable modes, selectable by the user before asking a question:

- **Pandas mode** (default): Generate a pandas snippet from the CSV data, execute locally, return the result. Idiomatic, supports all pandas operations, most users' first choice.
- **SQL mode** (Phase 2+): Generate a SQL query, load the CSV into an in-memory SQLite table, execute the query locally, return the result. Alternative for users comfortable with SQL, supports standard ANSI SQL operations.

Both modes:
- Load the full CSV data locally; only schema + capped sample + question reach Gemini
- Execute code locally on the full dataset; only the computed result (a table or scalar) returns to the UI
- Sandbox the generated code against the same threats (no imports/escapes, timeouts, size caps, restricted execution namespace)
- Expose the generated code in "Show its work"
- Handle the same analytical shapes: group-by aggregation, filter + aggregate, top-N, scalar (count/sum/mean/etc.)
- Fail gracefully on malformed input, unanswerable questions, and runtime errors

The **mode choice is user-selected and sent in the API request** (`mode: "pandas" | "sql"`); the agent branches on this field in the `generate_code` and `execute_code` nodes.

## Sandbox Security Model

Generated code (pandas or SQL) is **untrusted LLM output executed locally**, so it runs in a constrained namespace. The model (and its limits) are documented here explicitly for **both modes**:

### Pandas Sandbox (`src/analysis/sandbox.py`)

- **Bound names only.** The execution namespace exposes exactly: `df` (the full DataFrame), `pd` (pandas), and a small allow-list of safe builtins (`len`, `min`, `max`, `sum`, `sorted`, `round`, `abs`, `range`, `list`, `dict`, `set`, `str`, `int`, `float`, `bool`). `__builtins__` is replaced with this restricted mapping (no `open`, `eval`, `exec`, `__import__`, `compile`, `input`, `os`, `sys`).
- **No imports.** The generated source is statically rejected (AST scan) if it contains an `import` / `from ... import`, any dunder name (`__...__`, e.g. `__globals__`, `__class__`), or attribute access into `os`/`sys`/`subprocess`/`builtins`. A rejected snippet → categorized error, never executed.
- **Result contract.** The pandas snippet must assign its answer to a variable named `result`. The sandbox reads `result` after execution; absence of `result` is an error.
- **Timeout.** Execution runs under a wall-clock timeout (default 10s, `AGENT_EXEC_TIMEOUT`). Exceeding it aborts with a timeout error.
- **Result-size cap.** A returned table is capped (default 1000 rows, `AGENT_MAX_RESULT_ROWS`); larger results are truncated with a `truncated: true` flag (Phase 3). Scalars and small frames pass through.
- **Input caps.** Upstream, `profile_csv` enforces `AGENT_MAX_UPLOAD_BYTES` (5 MB) and `AGENT_MAX_ROWS` (200k) before any execution.

### SQL Executor (`src/analysis/sql_executor.py`, Phase 2+)

- **Table creation.** The CSV is loaded into an in-memory SQLite table with schema inferred from the first row (column names + types). The table is created within a transaction scoped to the request (exists only in memory for the duration of the run).
- **Query restrictions (static AST validation).** The generated SQL is checked for:
  - Only `SELECT` statements allowed (no `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, etc.)
  - No subqueries (prevents some indirect escapes; later relaxed if needed)
  - No multi-statement (semicolon-terminated) queries
  - No explicit file I/O functions (`LOAD_EXTENSION`, `ATTACH`, etc.)
  - Allowed operations: `SELECT`, `FROM`, `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`, `JOIN` (on the same table with CTEs or aliases), aggregate functions (`SUM`, `COUNT`, `AVG`, `MIN`, `MAX`), and scalar functions (`CAST`, `COALESCE`, `ABS`, string functions, date functions).
- **Execution context.** The query runs against the in-memory SQLite connection in a read-only mode (no mutations possible). A single result set is returned.
- **Result contract.** The query must produce a result set (one or more rows/columns). The result is normalized to a JSON-serializable `{columns: [...], rows: [[...]]}` table.
- **Timeout.** Execution runs under a wall-clock timeout (default 10s, same as pandas). Exceeding it aborts with a timeout error.
- **Result-size cap.** The returned table is capped at `AGENT_MAX_RESULT_ROWS` (default 1000); larger results are truncated with a `truncated: true` flag (Phase 3).

**Documented limits (honest about what this is and isn't):** this is a *defense-in-depth restriction for a single-user local tool*, not a hardened multi-tenant sandbox. It blocks the common dangerous primitives (imports, file/network, dunder traversal) and bounds time/size, but Python's `exec` is not a true security boundary — a determined adversary with arbitrary code could potentially find an escape. It is acceptable here because (a) the tool is single-user and local, (b) the code is generated from the *user's own* question against the *user's own* data, and (c) the AST allow-list plus restricted builtins remove the obvious escape hatches. If this ever became multi-tenant or remotely exposed, execution must move to a real isolation boundary (subprocess with seccomp, container, or WASM). This requirement is recorded as out-of-scope-but-known.

## Stack

> Concrete choices for this project. Generic rules (model-naming, DB driver, dev port, real-key tests) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12 (`requires-python >=3.11`; targets 3.12)
- **Agent framework:** LangGraph (`StateGraph`)
- **LLM provider + model:** Google Gemini / `gemini-2.5-flash` — configurable via `AGENT_LLM_MODEL` (provider auto-detected from `AGENT_GEMINI_API_KEY`; `AGENT_LLM_PROVIDER` may pin it)
- **Backend:** FastAPI + uvicorn (port 8001)
- **Database + ORM:** SQLite + SQLAlchemy 2.0 (+ Alembic). SQLite is the production driver for this single-user local tool; all gates run against it.
- **Frontend:** Next.js 15 static export (`output: 'export'`, `basePath: '/app'`), React 19, Tailwind v4, served single-origin by FastAPI at `/app`
- **Dependency management:** uv + `pyproject.toml` (frontend: pnpm)

| Key library | Version | Purpose |
|-------------|---------|---------|
| pandas | `>=2.2` | Parse the CSV and execute the generated computation **locally** over the full file. Chosen because it is the de-facto tabular-analysis library the LLM already knows, so generated snippets are idiomatic and correct; it keeps all computation on-machine (satisfies "data stays local"). |
| langgraph | `>=0.1` | Agent orchestration (already in skeleton) |
| google-genai | `>=2.9` | Gemini client (already in skeleton) |
| sqlalchemy / alembic | `>=2.0` / `>=1.13` | Persistence + migrations (already in skeleton) |

**Avoid:** sending the full DataFrame (or more than the capped sample) to any LLM (violates constraint 1); `eval`/`exec` without the AST allow-list + restricted builtins (violates the sandbox model); numpy-only or polars detours (pandas is sufficient and what the model writes natively); any second database or external store (SQLite local file only).

## Deployment Model

Long-running local service. Build the frontend once (`cd frontend && pnpm build` → `frontend/out/`), then run `uv run python -m src`, which starts uvicorn on **port 8001** and mounts the static export at `/app`. The canonical run + test URL is **http://localhost:8001/app/**. No cloud, no container, no external store — everything (data, DB, compute) is local.
