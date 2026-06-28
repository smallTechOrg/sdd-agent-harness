import { expect, test } from '@playwright/test'
import path from 'node:path'

// Resolve the fixture relative to this file (works regardless of cwd).
const CSV_FIXTURE = path.resolve(__dirname, '../fixtures/sales.csv')

// Phase-2 dataset-browser E2E against the LIVE app (real Gemini via .env, real
// DuckDB, real SQLite). Proves: datasets + their run history persist across a
// page reload (SQLite), the sidebar list is REAL and switchable, and re-opening
// a past run renders the PERSISTED answer instantly with NO new ask (no LLM).
test('persist across reload -> switch dataset -> re-open a past run from history', async ({
  page,
}) => {
  // ---------------------------------------------------------------------------
  // 1. Upload a CSV and ask a REAL question so there is run history to browse.
  // ---------------------------------------------------------------------------
  await page.goto('/app/')
  await expect(page.getByRole('heading', { name: 'Local Data Analyst' })).toBeVisible()

  await page.getByTestId('file-input').setInputFiles(CSV_FIXTURE)
  await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 60_000 })

  // The dataset must appear in the REAL sidebar list (not the old stub).
  const listItem = page.getByTestId('dataset-list-item').filter({ hasText: 'sales.csv' })
  await expect(listItem.first()).toBeVisible()

  const FIRST_Q = 'Which region had the highest total sales?'
  await page.getByTestId('question-input').fill(FIRST_Q)
  await page.getByTestId('ask-button').click()

  // Wait for the real agent answer; it must have completed, not failed.
  await expect(page.getByTestId('answer-panel')).toBeVisible({ timeout: 90_000 })
  await expect(page.getByTestId('ask-error')).toHaveCount(0)
  await expect(page.getByTestId('answer-failed')).toHaveCount(0)
  await expect(page.getByTestId('answer-success')).toBeVisible()

  // The question now appears in the run-history list (newest first).
  await expect(
    page.getByTestId('run-history-item').filter({ hasText: FIRST_Q }).first(),
  ).toBeVisible({ timeout: 90_000 })

  // Capture the persisted answer text + executed SQL so we can later assert the
  // re-opened run reproduces them EXACTLY (no new LLM call → identical content).
  const persistedAnswer = (
    await page.getByTestId('answer-success').locator('p').first().innerText()
  ).trim()
  expect(persistedAnswer.length).toBeGreaterThan(15)

  await page.getByTestId('show-its-work-toggle').click()
  const persistedSql = (await page.getByTestId('executed-sql').innerText()).trim()
  expect(persistedSql.toLowerCase()).toContain('select')

  // ---------------------------------------------------------------------------
  // 2. Reload the page -> the dataset STILL appears in the REAL sidebar list,
  //    proving persistence across a session (it's read back from SQLite).
  // ---------------------------------------------------------------------------
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Local Data Analyst' })).toBeVisible()

  // On a fresh load there is no active dataset yet, but the persisted list loads.
  const reloadedItem = page.getByTestId('dataset-list-item').filter({ hasText: 'sales.csv' })
  await expect(reloadedItem.first()).toBeVisible({ timeout: 60_000 })
  // It records that a question was asked (question_count > 0 persisted).
  await expect(reloadedItem.first()).toContainText(/question/)

  // ---------------------------------------------------------------------------
  // 3. Click the dataset in the sidebar -> profile re-loads and run-history
  //    shows the prior question (both pure DB reads — no LLM).
  // ---------------------------------------------------------------------------
  await reloadedItem.first().click()

  await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 60_000 })
  await expect(page.getByTestId('profile-card')).toContainText(/region/)
  // Selected item is marked active.
  await expect(reloadedItem.first()).toHaveAttribute('data-active', 'true')

  const historyItem = page.getByTestId('run-history-item').filter({ hasText: FIRST_Q })
  await expect(historyItem.first()).toBeVisible({ timeout: 30_000 })

  // ---------------------------------------------------------------------------
  // 4. Click the past run -> the persisted answer re-renders INSTANTLY from
  //    history (no new ask spinner, no LLM). Assert it matches the persisted
  //    content captured before reload.
  // ---------------------------------------------------------------------------
  await historyItem.first().click()

  const reopened = page.getByTestId('reopened-run')
  await expect(reopened).toBeVisible()
  // The "from history" marker proves this is a re-opened run, not a fresh ask.
  await expect(page.getByTestId('from-history-label')).toBeVisible()
  // No ask spinner appeared — re-opening is instant (pure DB read).
  await expect(page.getByTestId('ask-loading')).toHaveCount(0)
  await expect(page.getByTestId('ask-error')).toHaveCount(0)

  // The persisted answer text is reproduced exactly (it came from the stored
  // record, not a new model call).
  const reopenedAnswer = (
    await reopened.getByTestId('answer-success').locator('p').first().innerText()
  ).trim()
  expect(reopenedAnswer).toBe(persistedAnswer)

  // The persisted summary table re-renders with real rows.
  const reopenedTable = reopened.getByTestId('summary-table')
  await expect(reopenedTable).toBeVisible()
  expect(await reopenedTable.locator('tbody tr').count()).toBeGreaterThan(0)

  // Show-its-work re-opens with the SAME persisted DuckDB SQL.
  await reopened.getByTestId('show-its-work-toggle').click()
  await expect(reopened.getByTestId('executed-sql')).toContainText(/select/i)
  const reopenedSql = (await reopened.getByTestId('executed-sql').innerText()).trim()
  expect(reopenedSql).toBe(persistedSql)

  // ---------------------------------------------------------------------------
  // 5. Upload a SECOND dataset and ask on it, then switch back — the active
  //    profile + history change with the selection.
  // ---------------------------------------------------------------------------
  await page.getByTestId('file-input').setInputFiles(CSV_FIXTURE)
  await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 60_000 })

  // There are now (at least) two datasets in the list.
  expect(await page.getByTestId('dataset-list-item').count()).toBeGreaterThanOrEqual(2)

  const SECOND_Q = 'What is the total number of rows of sales data?'
  await page.getByTestId('question-input').fill(SECOND_Q)
  await page.getByTestId('ask-button').click()
  await expect(page.getByTestId('answer-success')).toBeVisible({ timeout: 90_000 })
  await expect(
    page.getByTestId('run-history-item').filter({ hasText: SECOND_Q }).first(),
  ).toBeVisible({ timeout: 90_000 })

  // Switch to the FIRST dataset's history by clicking the run-history-bearing
  // item. Both list items are "sales.csv"; selecting the one whose history has
  // FIRST_Q proves switching changes the active history. We click each item and
  // assert the history reflects the selection.
  const items = page.getByTestId('dataset-list-item')
  const count = await items.count()
  let foundFirstHistory = false
  for (let i = 0; i < count; i++) {
    await items.nth(i).click()
    await expect(page.getByTestId('profile-card')).toBeVisible({ timeout: 30_000 })
    // Give the history fetch a moment to settle for this selection.
    const hasFirst =
      (await page.getByTestId('run-history-item').filter({ hasText: FIRST_Q }).count()) > 0
    if (hasFirst) {
      foundFirstHistory = true
      // Selecting it cleared the previously-shown answer (a switch resets it).
      await expect(page.getByTestId('reopened-run')).toHaveCount(0)
      break
    }
  }
  expect(foundFirstHistory).toBe(true)

  // ---------------------------------------------------------------------------
  // 6. The remaining "coming soon" stubs are STILL present and labelled, visibly
  //    distinct from the now-REAL dataset list and run history.
  // ---------------------------------------------------------------------------
  const stubBadges = page.getByTestId('stub-badge')
  expect(await stubBadges.count()).toBeGreaterThan(0)
  await expect(stubBadges.first()).toContainText(/coming soon/i)
  // The real dataset list is NOT a stub (no data-stub on it).
  await expect(page.getByTestId('dataset-list')).not.toHaveAttribute('data-stub', 'true')
  // Daily-cost roll-up stub still shows the placeholder dash.
  await expect(page.getByTestId('daily-cost')).toHaveText('—')
})
