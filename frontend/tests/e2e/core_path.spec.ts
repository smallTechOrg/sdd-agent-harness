import { test, expect } from '@playwright/test'
import path from 'node:path'

/**
 * Phase 1 E2E smoke test of the core path: upload → ask → answer-with-SQL.
 *
 * Runs against the LIVE app served by FastAPI at http://localhost:8001/app/
 * (configured via baseURL in playwright.config.ts). The backend must be booted
 * with the built frontend (`pnpm build` then `uv run python -m src`).
 *
 * Asserts REAL CONTENT — actual dataset summary, a real answer, and real SQL —
 * not merely HTTP status.
 */

const SAMPLE_CSV = path.resolve(__dirname, '../../../samples/sales.csv')

test('upload a CSV, ask a question, and read the answer with exact SQL', async ({ page }) => {
  await page.goto('/app/')

  // Header is present and the page is styled (REAL).
  await expect(page.getByRole('heading', { name: 'Local Data Analyst' })).toBeVisible()

  // The question box is disabled until a dataset is loaded.
  await expect(page.getByTestId('ask-button')).toBeDisabled()

  // Coming-soon stubs are visible and clearly labelled (never mistaken for bugs).
  const pills = page.getByTestId('coming-soon-pill')
  await expect(pills.first()).toBeVisible()
  expect(await pills.count()).toBeGreaterThan(0)
  await expect(page.getByTestId('coming-soon-stubs')).toContainText('Coming soon')

  // Upload the sample CSV.
  await page.getByTestId('file-input').setInputFiles(SAMPLE_CSV)
  await page.getByTestId('upload-button').click()

  // Dataset summary renders with REAL content: row count + a real column name.
  const summary = page.getByTestId('dataset-summary')
  await expect(summary).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('dataset-rowcount')).toContainText('rows')
  await expect(page.getByTestId('dataset-columns')).toContainText('revenue')

  // Ask a question. The Ask button stays disabled until a question is typed
  // (canAsk requires question.trim().length > 0), so fill FIRST, then assert.
  await page.getByTestId('question-input').fill('What is the total revenue?')
  await expect(page.getByTestId('ask-button')).toBeEnabled()
  await page.getByTestId('ask-button').click()

  // The answer panel renders a non-empty plain-English answer (REAL).
  const answer = page.getByTestId('answer-text')
  await expect(answer).toBeVisible({ timeout: 45_000 })
  const answerText = (await answer.innerText()).trim()
  expect(answerText.length).toBeGreaterThan(0)

  // The Exact SQL block shows real SQL (contains a SELECT).
  const sql = page.getByTestId('answer-sql')
  await expect(sql).toBeVisible()
  await expect(sql).toContainText(/select/i)
})
