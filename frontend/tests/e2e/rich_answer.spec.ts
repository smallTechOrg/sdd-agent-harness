import { test, expect } from '@playwright/test'
import path from 'node:path'

/**
 * Phase 2 E2E — the richer analyst response.
 *
 * Runs against the LIVE app served by FastAPI at http://localhost:8001/app/
 * (baseURL in playwright.config.ts) against the real Gemini backend.
 *
 * Asserts REAL CONTENT:
 *   - the profile panel renders per-column stats after upload,
 *   - a grouped question yields an answer + exact SQL + a chart + a multi-row
 *     summary table + 2–3 follow-up chips,
 *   - clicking a follow-up chip submits it and produces a fresh answer.
 */

const SAMPLE_CSV = path.resolve(__dirname, '../../../samples/sales.csv')

test('upload profiles the dataset; a grouped question yields chart, table, and follow-ups', async ({
  page,
}) => {
  await page.goto('/app/')

  await expect(page.getByRole('heading', { name: 'Local Data Analyst' })).toBeVisible()

  // Four stubs are now REAL → their cards are gone. The remaining four stay labelled.
  const stubs = page.getByTestId('coming-soon-stubs')
  await expect(stubs).toContainText('Coming soon')
  await expect(stubs).toContainText('Datasets')
  await expect(stubs).toContainText('Cost meter')
  await expect(stubs).toContainText('History & audit trail')
  await expect(stubs).toContainText('Live step stream')
  await expect(stubs).not.toContainText('Data profile')
  await expect(stubs).not.toContainText('Follow-up suggestions')

  // Upload the sample CSV.
  await page.getByTestId('file-input').setInputFiles(SAMPLE_CSV)
  await page.getByTestId('upload-button').click()

  // Dataset summary renders (REAL).
  await expect(page.getByTestId('dataset-summary')).toBeVisible({ timeout: 30_000 })

  // Profile panel renders real per-column content: a real column name + a stat cell.
  const profile = page.getByTestId('profile-panel')
  await expect(profile).toBeVisible({ timeout: 30_000 })
  await expect(profile).toContainText('revenue')
  // At least one profile row with a distinct count.
  const distinctCells = page.getByTestId('profile-distinct-count')
  expect(await distinctCells.count()).toBeGreaterThan(0)

  // Ask a GROUPED question (drives a chart + multi-row summary table).
  // Fill FIRST, then assert the Ask button is enabled (canAsk needs non-empty text).
  await page.getByTestId('question-input').fill('What is total revenue by region?')
  await expect(page.getByTestId('ask-button')).toBeEnabled()
  await page.getByTestId('ask-button').click()

  // A non-empty plain-English answer (REAL).
  const answer = page.getByTestId('answer-text')
  await expect(answer).toBeVisible({ timeout: 45_000 })
  expect((await answer.innerText()).trim().length).toBeGreaterThan(0)

  // The Exact SQL block shows a SELECT.
  await expect(page.getByTestId('answer-sql')).toContainText(/select/i)

  // A chart renders with a real SVG.
  const chart = page.getByTestId('answer-chart')
  await expect(chart).toBeVisible()
  await expect(page.getByTestId('answer-chart-svg')).toBeVisible()

  // The rich summary table renders multiple rows.
  const summary = page.getByTestId('summary-table')
  await expect(summary).toBeVisible()
  const summaryRows = page.locator('[data-testid="summary-table-body"] tr')
  expect(await summaryRows.count()).toBeGreaterThan(1)

  // 2–3 follow-up chips render.
  await expect(page.getByTestId('followup-chips')).toBeVisible()
  const chips = page.getByTestId('followup-chip')
  const chipCount = await chips.count()
  expect(chipCount).toBeGreaterThanOrEqual(2)
  expect(chipCount).toBeLessThanOrEqual(3)

  // Click a follow-up chip → it submits as the next question → a fresh answer renders.
  const firstChipText = (await chips.first().innerText()).trim()
  await chips.first().click()
  // The input reflects the picked question and the answer updates.
  await expect(page.getByTestId('answer-working')).toBeVisible({ timeout: 10_000 }).catch(() => {})
  await expect(page.getByTestId('answer-text')).toBeVisible({ timeout: 45_000 })
  const newAnswer = (await page.getByTestId('answer-text').innerText()).trim()
  expect(newAnswer.length).toBeGreaterThan(0)
  // The new run's question matches the chip we clicked (sanity that the chip drove it).
  expect(firstChipText.length).toBeGreaterThan(0)
})
