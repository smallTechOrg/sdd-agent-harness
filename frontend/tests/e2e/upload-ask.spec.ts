import { expect, test } from '@playwright/test'
import path from 'node:path'

// Phase-1 gate. Runs against the LIVE app at http://localhost:8001/app/ with the
// real Gemini key (the orchestrator boots the server before this runs). Asserts
// RENDERED content end-to-end: profile → ask → answer text + chart + table +
// collapsible code panel + cost line. Not just an HTTP 200.

const CSV_PATH = path.resolve(__dirname, '../../../examples/sales.csv')

test('upload a CSV, ask a question, see a real answer', async ({ page }) => {
  await page.goto('http://localhost:8001/app/')

  // Page loads and is styled (header present).
  await expect(page.getByRole('heading', { name: 'Pandora' })).toBeVisible()

  // Upload a real CSV via the hidden file input.
  await page.getByTestId('file-input').setInputFiles(CSV_PATH)

  // Profile card renders with row/column counts.
  const profile = page.getByTestId('profile-card')
  await expect(profile).toBeVisible({ timeout: 60_000 })
  await expect(page.getByTestId('profile-counts')).toContainText('rows')
  await expect(page.getByTestId('profile-counts')).toContainText('columns')

  // Ask a question (typed — independent of whatever suggestions the model returns).
  await page.getByTestId('ask-input').fill('What is total revenue by region?')
  await page.getByTestId('ask-button').click()

  // A live step trace appears quickly (feedback within ~100ms of submit).
  await expect(page.getByTestId('step-trace')).toBeVisible({ timeout: 10_000 })

  // The answer arrives (Gemini + sandbox can take ~30s).
  const answerPanel = page.getByTestId('answer-panel')
  await expect(answerPanel).toBeVisible({ timeout: 90_000 })

  // Answer text is rendered (non-empty markdown).
  const answerText = page.getByTestId('answer-text')
  await expect(answerText).toBeVisible()
  await expect(answerText).not.toBeEmpty()

  // A chart element. Recharts renders the main plot as <svg.recharts-surface>,
  // plus a second tiny <svg.recharts-surface> inside the <Legend> — so scope to
  // the first (main) surface to avoid a strict-mode 2-match violation.
  await expect(
    page.getByTestId('chart').locator('svg.recharts-surface').first(),
  ).toBeVisible()

  // A summary table is present.
  await expect(page.getByTestId('summary-table')).toBeVisible()

  // The collapsible code panel exists — expand it and assert real code text.
  await page.getByTestId('code-toggle').click()
  const codeText = page.getByTestId('code-text')
  await expect(codeText).toBeVisible()
  await expect(codeText).not.toBeEmpty()

  // The cost line is present.
  await expect(page.getByTestId('cost-line')).toContainText('tokens')
  await expect(page.getByTestId('cost-line')).toContainText('Today:')
})

test('labelled Phase 2/3/4 stubs are present and disabled', async ({ page }) => {
  await page.goto('http://localhost:8001/app/')

  // History stub — visible, badged Phase 2.
  await expect(page.getByTestId('history-stub')).toContainText('Coming in Phase 2')

  // Upload first so the multi-file + deep-analysis stubs render.
  await page.getByTestId('file-input').setInputFiles(CSV_PATH)
  await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 60_000 })

  // Multi-file stub — disabled, badged Phase 3.
  const multifile = page.getByTestId('multifile-stub')
  await expect(multifile).toContainText('Multi-file — Phase 3')
  await expect(multifile.getByRole('button')).toBeDisabled()

  // Deep analysis toggle — disabled, badged Phase 4.
  await expect(page.getByText('Deep analysis (plan & iterate)')).toBeVisible()
  await expect(page.getByText('Phase 4', { exact: true })).toBeVisible()
})
