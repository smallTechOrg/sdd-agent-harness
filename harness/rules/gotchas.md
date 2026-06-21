# Gotchas — encoded institutional memory

Hard-won fixes from real builds. Each one was a live failure that cost rework. **Read the
section for your stack before Iteration 0** — the point of this file is that a build never
re-derives a trap a previous build already paid for.

Each entry has a stable **ID** (so gates and reviews can cite it), then **Trap → Fix**. When
a build hits a *new* trap, add an entry here (same shape, next ID) before closing the build —
that is how the harness stays smarter than any single run. The recipes and the reviewer gate
reference these IDs; see [working-with-llms.md](../patterns/working-with-llms.md) for LLM depth.

---

## Python packaging & `uv`

- **[C-HATCH-PKG]** Hatchling can't find `src/` — install fails with "Unable to determine
  which files to ship."
  → Add to `pyproject.toml`: `[tool.hatch.build.targets.wheel]` / `packages = ["src"]`.

- **[C-MULTIPART]** FastAPI form / file upload 500s with "python-multipart not installed."
  → Add `python-multipart` to `dependencies` whenever the app accepts uploads or form posts.

- **[C-UV-DEV]** `uv run` ignores dev deps in `[project.optional-dependencies].dev`.
  → Run tests with `uv run --extra dev pytest`.

## Config & environment

- **[C-ENV-EXTRA]** pydantic-settings crashes on unknown env vars.
  → `model_config = SettingsConfigDict(..., extra="ignore")`.

- **[C-ENV-STRIP]** Inline `#` comments leak into env values: `PROVIDER=stub  # default` is
  read as the literal `"stub  # default"`.
  → Strip in a resolver property: `value.split("#")[0].strip()`. Never trust the raw value.

- **[C-PORT-8001]** Port 8000 collides with other local servers/proxies.
  → Default dev port is **8001** for every recipe; keep it configurable via env.

- **[C-HEALTH-PROVIDER]** A bare `{"status":"ok"}` health check can't tell you whether stub
  mode is active from the outside.
  → `/health` returns `llm_provider` and `stub_mode` so you can verify offline mode by curl.

- **[C-SECRET]** Secrets logged by accident.
  → Use `pydantic.SecretStr` for every key; record only a boolean in the session report —
  never the value. See [secret-hygiene.md](secret-hygiene.md).

## Databases — SQLite or DuckDB (local-first, no server)

The boilerplate ships **two local stores**; pick by need. There is no Postgres/server recipe —
add one only on real demand. Both bootstrap schema with `create_tables()` (SQLAlchemy
`create_all`) at startup — no migrations shipped.

| Need | Store | Recipe |
|------|-------|--------|
| Relational / transactional | **SQLite** | `python-fastapi-sqlite` |
| Analytics (CSV/Parquet/JSON, columnar) | **DuckDB** (+ a SQLite spine for metadata) | `python-fastapi-duckdb` |

- **[C-DB-SAME-AS-PROD]** Test on the **store you actually ship**, never a convenient
  substitute. Both recipes ship green on their own store (SQLite for the relational recipe,
  DuckDB + SQLite for the analytics recipe). The classic trap is testing on SQLite while
  shipping a *different* engine — so if you ever add a server DB, run its tests on that engine,
  not SQLite. A [non-negotiable](non-negotiables.md).

## Migrations (opt-in — not shipped)

`create_tables()` is enough for a local-first start. If you add Alembic later, these still bite:

- **[C-ALEMBIC]** A missing `alembic/script.py.mako` makes `revision --autogenerate` fail
  cryptically. → Ship `script.py.mako`; gate on `revision` → `upgrade head` → `current`.
- **[C-ALTER-DEFAULT]** An `ALTER TABLE … ADD COLUMN NOT NULL` with no default fails on a
  populated table. → Add a `server_default` (NULL/constant), backfill, then drop it.

## Databases — DuckDB (analytics / local-first)

- **[C-DUCKDB-RECIPE]** Analytics is not the relational recipe with the engine swapped —
  forcing a SQLAlchemy/relational scaffold to do columnar file queries means rewriting `db/`
  and the query path (adapting the wrong recipe burned ~30% of one Iteration 0).
  → Use the `python-fastapi-duckdb` recipe; don't adapt `python-fastapi-sqlite`.

- **[C-DUCKDB-VIEW]** DuckDB views are connection-scoped — a `CREATE VIEW` is gone after a
  server restart even though the file and the `datasets` row remain ("table or view not
  found").
  → Persist data with `CREATE OR REPLACE TABLE` (not a view), or re-create views at startup
  in the FastAPI `lifespan`. The DuckDB recipe uses persistent tables.

- **[C-DB-DIRNAME]** `os.makedirs(dirname(path))` crashes on a bare filename
  (`os.path.dirname("x.duckdb")` → `""` → `FileNotFoundError`).
  → Guard: `if dirname: os.makedirs(dirname, exist_ok=True)`.

- **[C-EXCEL-TMP]** Excel ingest via an adjacent temp CSV leaks files the view still
  references.
  → Use `tempfile.mkdtemp()` or convert to Parquet in memory.

## LLM providers (Gemini)

- **[C-LLM-SDK]** `google-generativeai` is deprecated (raises `FutureWarning`, unmaintained).
  → Use **`google-genai`** (`from google import genai`):
  `client = genai.Client(api_key=key); client.models.generate_content(...)`.

- **[C-LLM-FENCE]** Gemini wraps JSON in ```` ```json ```` fences even when told "JSON only."
  → Strip the opening/closing fence lines in `complete()` before `json.loads`.

- **[C-LLM-MODEL]** Model names go stale *fast* — the Gemini Flash line moved
  `1.5-flash → 2.0-flash → 2.5-flash → 3.1-flash-lite` across 2025–2026, each break
  deprecating the last.
  → Keep the model in config, never hardcoded. `gemini-2.5-flash` is the safe documented
  default; confirm the current id against the provider / the `claude-api` skill before a real
  run. See [working-with-llms.md](../patterns/working-with-llms.md) and
  [google-genai.md](../../spec/patterns/google-genai.md).

- **[C-SESSION-COMMIT]** A FastAPI `BackgroundTask` (or any queued async work) that reads a
  row the request just wrote can race a still-open DB session and see nothing.
  → Commit the request's session **before** queuing background work that depends on it.

- **[C-STUB]** The offline gate must never call a real model — a green stub run that secretly
  hit the network burns keys and lies about being offline.
  → Default `…_LLM_PROVIDER=stub`; add a hard `ALLOW_MODEL_REQUESTS=False` guard in test
  `conftest.py`.

- **[C-STUB-BANNER]** A human viewer can mistake stub output for real AI output.
  → Every UI page shows a visible banner while the provider is stubbed.

## Frontend (Next.js)

- **[C-MD-RENDER]** A GFM table dropped into `<pre>` shows literal `|` and `---`.
  → Render with `react-markdown` (+ `remark-gfm`, with `table`/`th`/`td` overrides), not `<pre>`.

- **[C-MD-XSS]** Enabling raw HTML in a markdown renderer to "make it render" opens an XSS
  hole — LLM/user content reaches `dangerouslySetInnerHTML`.
  → Keep `html: false` / no `rehype-raw` on untrusted content; render via the AST, not raw HTML.

- **[C-PLOTLY-SSR]** `react-plotly.js` needs `window` and breaks SSR.
  → `dynamic(() => import('react-plotly.js'), { ssr: false })`.

- **[C-SSR-BROWSER-API]** Any browser-only API (`localStorage`, `sessionStorage`, `window`,
  `document`, `crypto`, `navigator`) read at **module top-level** or inside a `useState`/`useRef`
  **initialiser** crashes the Next.js server render — those initialisers run during SSR, where the
  API is `undefined`. This shipped a real `localStorage.getItem is not a function` 500 that
  `npm run build` did **not** catch (build prerenders, it does not exercise the request path).
  → Read browser APIs only inside `useEffect` (client-only), or guard every access with
  `typeof window !== 'undefined'`. **`npm run build` passing is not proof the page renders** —
  the gate must `npm run start` and GET the page (see [testing.md](testing.md) Live-server gate).

- **[C-SESSION-SCOPE]** Hardcoded `session_id: 'default'` makes every browser tab share one
  conversation.
  → Generate a per-tab id once: `crypto.randomUUID()` in a `useRef`/`useState` initialiser,
  with a `Math.random` fallback for non-secure contexts. **SSR trap:** that initialiser runs on
  the server too — if you persist the id to `localStorage`, do the read/write in a `useEffect`,
  never in the initialiser, or you hit [C-SSR-BROWSER-API]. This exact combination shipped the
  500 above.

- **[C-API-URL]** `NEXT_PUBLIC_API_URL` is the only backend-URL env the browser can read.
  → Fall back to `http://localhost:8001` for local dev; never hardcode a deployed URL.

## Layout, docs & delivery

- **[C-LAYOUT]** Repo root *is* the project — no `app/` nesting. All application code in
  `src/`, tests in `tests/` at the root. See [layout.md](../layout.md).

- **[C-README]** The README is written in Iteration 0, not deferred — a repo whose README
  never gets updated leaves a cloner unable to run it (a "docs must be true"
  [non-negotiable](non-negotiables.md)). Iteration 0's deliverable includes a working quickstart.

- **[C-COPY-PASTE]** Non-coders need copy-paste commands, not instructions like "create a
  `.env` with `KEY=…`."
  → Give the exact command, what success looks like, what to do on failure. The executor
  creates `.env` from `.env.example` and prints a one-line "edit this, replace `your-key-here`."

- **[C-GIT-ADD]** `git add -A` sweeps in stray files (`data/`, `.venv`).
  → Stage specific paths only. See [git-and-delivery.md](git-and-delivery.md).
