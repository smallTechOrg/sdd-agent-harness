import { defineConfig, devices } from '@playwright/test'

/**
 * E2E config for the Data Analysis Agent frontend.
 * Tests run against the static export served by a local HTTP server.
 *
 * The static output is in `out/` (basePath '/app' only applies when
 * served behind FastAPI — for testing we serve it directly).
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3099',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm exec serve out -l 3099 --no-clipboard',
    url: 'http://localhost:3099',
    reuseExistingServer: false,
    timeout: 30000,
    stdout: 'ignore',
    stderr: 'ignore',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
