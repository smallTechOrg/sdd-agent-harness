import { defineConfig, devices } from '@playwright/test'

// The orchestrator/qa boots FastAPI on :8001 (which serves the static export at
// /app/) with the real Gemini key from .env BEFORE running these tests. We do NOT
// start a webServer here.
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:8001/app/',
    trace: 'on-first-retry',
    actionTimeout: 45_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
