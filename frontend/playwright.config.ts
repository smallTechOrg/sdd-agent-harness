import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for the Local Data Analyst E2E smoke test.
 *
 * The app is a Next.js STATIC EXPORT served by the FastAPI backend at
 * http://localhost:8001/app/ — NOT by a Next dev server. So:
 *   - baseURL points at the FastAPI host (http://localhost:8001).
 *   - There is NO `webServer` block: we do not auto-start `next dev`.
 *
 * Before running these tests the harness (agent-builder / qa-auditor) must:
 *   1. Build the frontend:  cd frontend && pnpm build   (produces frontend/out/)
 *   2. Boot the backend:    uv run python -m src         (serves out/ at /app/)
 * Then:  cd frontend && npx playwright test tests/e2e/
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 60_000,
  expect: { timeout: 45_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8001',
    trace: 'on-first-retry',
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
