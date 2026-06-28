import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for the DataChat Phase 1 headless E2E gate.
 *
 * The roadmap gate runs, from the REPO ROOT:
 *   uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm build) \
 *     && uv run python -m src &   # background the live server on :8001
 *   npx playwright test tests/e2e/ --reporter=line
 *
 * This config also stands alone: the `webServer` block boots the same backend
 * (`uv run python -m src`, which serves the built Next.js static export at
 * `/app/` and the `/api` routes) and, because `reuseExistingServer: true`, it
 * reuses a server the gate already started instead of fighting it for :8001.
 *
 * The run is REAL end-to-end: a live FastAPI server, the built frontend, and
 * real Gemini round-trips. Nothing is mocked — that is the whole point of the
 * gate. Gemini answers take several seconds, so timeouts are generous.
 *
 * Prerequisites the gate satisfies (do them yourself if running standalone):
 *   - `uv run alembic upgrade head`  (DB schema applied)
 *   - `cd frontend && pnpm build`    (frontend built to frontend/out/)
 *   - `.env` populated with AGENT_GEMINI_API_KEY (real key — never committed)
 */
export default defineConfig({
  testDir: './tests/e2e',
  // Generous per-test budget: a real Gemini plan→code→execute→synthesize round
  // trip is several seconds; the full ask test waits on streamed tokens.
  timeout: 120_000,
  expect: {
    // Individual assertions (e.g. waiting for the streamed answer to appear)
    // get a long timeout to absorb real LLM latency.
    timeout: 60_000,
  },
  // The journey is stateful (upload → ask → answer); never parallelise within it.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:8001/app/',
    headless: true,
    actionTimeout: 30_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // Boot the real single-origin server from the repo root. `python -m src`
    // serves the built static frontend at /app/ and the /api routes on :8001.
    command: 'uv run python -m src',
    cwd: __dirname,
    url: 'http://localhost:8001/app/',
    // Reuse the server the gate backgrounds; only boot one ourselves standalone.
    reuseExistingServer: true,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
