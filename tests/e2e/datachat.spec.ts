import { test, expect, type Page } from '@playwright/test'
import path from 'node:path'

/**
 * DataChat — Phase 1 headless E2E gate.
 *
 * Drives the REAL app: a live FastAPI server (`uv run python -m src`) serving
 * the built Next.js static export at http://localhost:8001/app/, the `/api`
 * routes, and a real Gemini round-trip. Nothing is mocked. The point of this
 * gate is to prove the owner's exact primary journey works first-time:
 *
 *   empty state → upload a CSV → auto-profile → ask a question →
 *   step indicator advances → streamed plain-English answer with real numbers →
 *   key numbers + summary table → expand "Show code" → tokens + cost →
 *   and that the deferred features render as clearly-labelled STUBS (not bugs).
 *
 * Run (from the repo root, with the server already built + migrated):
 *   uv run python -m src &                                  # background server
 *   npx playwright test tests/e2e/ --reporter=line
 * The webServer block in playwright.config.ts also boots/ reuses the server, so
 * this also runs fully standalone.
 *
 * Fixture: tests/fixtures/small_sales.csv (6 rows) — real but fast. Its real
 * columns are: region, product, revenue, units.
 *
 * Flake mitigation: real Gemini latency is several seconds, so the streamed
 * answer + done event are awaited with long (60s) assertion timeouts. Stream
 * completion is detected by the per-question cost line appearing (gated on
 * `!streaming`, and durable across the post-run thread rehydrate) rather than by
 * the "Ask" button — which is disabled whenever the input is empty, so it stays
 * disabled right after submit regardless of stream state.
 */

// Playwright loads specs in a CommonJS context here, so `__dirname` is
// available directly — no need for import.meta.url.
const SMALL_CSV = path.resolve(__dirname, '../fixtures/small_sales.csv')

/** Long budget for a real plan→code→execute→synthesize Gemini round-trip. */
const ASK_TIMEOUT = 60_000

/**
 * Shared setup: load the empty state, upload the CSV, and wait for the
 * workbench (profile panel + question input) to appear. Returns nothing —
 * leaves the page on the loaded workbench.
 */
async function uploadAndOpenWorkbench(page: Page): Promise<void> {
  // './' resolves against the baseURL's /app/ path → http://localhost:8001/app/
  // ('/' would drop the basePath and hit the bare origin, which 404s).
  await page.goto('./')

  // Upload via the hidden file input (setInputFiles works on hidden inputs).
  await page.locator('input[type="file"]').setInputFiles(SMALL_CSV)

  // The workbench appears once the profile loads — the question input is the
  // clearest signal that the upload+profile round-trip succeeded.
  await expect(
    page.getByPlaceholder('Ask a question about this dataset…'),
  ).toBeVisible({ timeout: 30_000 })
}

test.describe('DataChat primary journey', () => {
  test('empty state, upload, and auto-profile render real data', async ({
    page,
  }) => {
    // 1. Empty state renders with the upload prompt + privacy promise.
    // './' resolves against the baseURL's /app/ path → http://localhost:8001/app/
    // ('/' would drop the basePath and hit the bare origin, which 404s).
    await page.goto('./')

    await expect(
      page.getByRole('heading', { name: 'Upload a CSV to start' }),
    ).toBeVisible()
    await expect(
      page.getByText(
        /only the column names and a few sample\s+rows are sent to the model/i,
      ),
    ).toBeVisible()
    // The product name is on the page.
    await expect(page.getByText('DataChat', { exact: true })).toBeVisible()

    // 2. Upload the CSV → the profile panel populates with REAL data.
    await page.locator('input[type="file"]').setInputFiles(SMALL_CSV)

    // Wait for the workbench (question input) to appear.
    await expect(
      page.getByPlaceholder('Ask a question about this dataset…'),
    ).toBeVisible({ timeout: 30_000 })

    // Profile panel: the row count (6 data rows in small_sales.csv).
    await expect(page.getByText('Rows', { exact: true })).toBeVisible()
    // The right profile panel shows the real row count.
    await expect(
      page.locator('aside').filter({ hasText: 'Rows' }).getByText('6', { exact: true }).first(),
    ).toBeVisible()

    // Real column names from the CSV appear in the profile.
    for (const col of ['region', 'product', 'revenue', 'units']) {
      await expect(page.getByText(col, { exact: true }).first()).toBeVisible()
    }

    // The "what was sent to the model" privacy reassurance is present.
    await expect(
      page.getByText('What was sent to the model', { exact: true }),
    ).toBeVisible()
  })

  test('ask a question → streamed real answer with numbers, table, code, cost', async ({
    page,
  }) => {
    await uploadAndOpenWorkbench(page)

    // 3. Type a real question referencing real columns and send it. "by region"
    // yields BOTH a grouped summary table and key numbers, exercising the full
    // result surface (the total-revenue of small_sales.csv is 900).
    const input = page.getByPlaceholder('Ask a question about this dataset…')
    await input.click()
    await input.fill('What is the total revenue for each region?')

    const askButton = page.getByRole('button', { name: 'Ask', exact: true })
    await expect(askButton).toBeEnabled()
    await askButton.click()

    // 4. The step indicator advances: at least one real step label appears.
    // (Planning… → Generating code… → Running locally… → Writing answer…)
    await expect(
      page
        .getByText(/Planning…|Generating code…|Running locally…|Writing answer…/)
        .first(),
    ).toBeVisible({ timeout: ASK_TIMEOUT })

    // Completion signal: the per-question tokens + cost line renders ONLY once
    // the run is done (it is gated on `!streaming`). Waiting for the `$`-prefixed
    // cost is the robust, DURABLE way to know the real Gemini stream finished:
    //   - the "Ask" button is NOT reliable (it is disabled whenever the input is
    //     empty, which it is right after submit), and
    //   - the prompt/completion-token spans only show on the transient live turn;
    //     after onRunComplete rehydrates the thread from GET /api/datasets/{id}
    //     (whose message shape carries cost_usd but not token counts), only the
    //     cost remains. So the cost line is the stable post-completion signal.
    // This wait absorbs the several-second real LLM latency.
    const costLine = page.getByText(/\$\d+\.\d+/).last()
    await expect(costLine).toBeVisible({ timeout: ASK_TIMEOUT })
    // The cost is a real, NON-zero amount (a real Gemini run always spends > $0).
    const costText = (await costLine.innerText()).trim()
    const costMatch = costText.match(/\$(\d+\.\d+)/)
    expect(costMatch).not.toBeNull()
    expect(Number(costMatch![1])).toBeGreaterThan(0)

    // The answer block contains a real, non-empty plain-English answer that
    // references a digit (a real number — not an empty placeholder/spinner).
    const answerBlock = page.locator('p.whitespace-pre-wrap').last()
    await expect(answerBlock).toBeVisible()
    const answerText = (await answerBlock.innerText()).trim()
    expect(answerText.length).toBeGreaterThan(0)
    expect(answerText).toMatch(/\d/) // contains a real number

    // 5. The key-numbers strip and/or summary table render with real values.
    // For a "by region" question the agent emits a grouped result table; assert
    // a real table with a region name + a numeric cell is shown.
    const summaryTable = page.locator('table')
    const keyNumberCards = page.locator('.tabular-nums')
    const hasTable = (await summaryTable.count()) > 0
    const hasKeyNumbers = (await keyNumberCards.count()) > 0
    expect(hasTable || hasKeyNumbers).toBeTruthy()
    // A real region value from the CSV appears in the rendered result.
    await expect(
      page.getByText(/North|South|East|West/).first(),
    ).toBeVisible()

    // 6. The executed pandas is revealed, and contains `df` + `result`.
    //
    // The DURABLE source of the code is the run-history audit trail: once a run
    // completes, the live thread rehydrates from GET /api/datasets/{id} (whose
    // message shape carries the answer/table/cost but NOT the generated code or
    // token counts — those live behind GET /api/messages/{id}). So we open the
    // History tab, expand the just-completed run, and assert the revealed code.
    // This also matches the spec's "expand a history row → full plan/code/result"
    // and is race-free (unlike the transient inline "Show code" on the live turn).
    await page.getByRole('button', { name: /^History/ }).click()
    // The just-completed run appears in the history list — expand it.
    const historyRow = page
      .getByRole('button', { name: /total revenue for each region/i })
      .last()
    await expect(historyRow).toBeVisible({ timeout: ASK_TIMEOUT })
    await historyRow.click()

    // The run detail loads (GET /api/messages/{id}) and shows the code panel,
    // which renders expanded (defaultOpen) in the audit trail.
    const codeBlock = page.locator('pre code').last()
    await expect(codeBlock).toBeVisible({ timeout: ASK_TIMEOUT })
    const codeText = await codeBlock.innerText()
    expect(codeText).toContain('df')
    expect(codeText).toContain('result')
    // The collapsible "Show code"/"Hide code" toggle is wired in the same panel.
    await expect(
      page.getByRole('button', { name: /^(Show|Hide) code$/ }).last(),
    ).toBeVisible()

    // 7. The tokens + cost line shows real numbers. The run-history detail is the
    // durable home of the per-question prompt + completion TOKEN counts (the live
    // turn drops them on rehydrate). Assert real non-zero token counts and cost.
    await expect(page.getByText(/\d[\d,]*\s+prompt\b/).last()).toBeVisible()
    await expect(page.getByText(/\d[\d,]*\s+completion\b/).last()).toBeVisible()
    // The cost line (asserted non-zero above) is still on screen.
    await expect(page.getByText(/\$\d+\.\d+/).last()).toBeVisible()

    // 8. Labelled STUBS render as clearly-marked previews (not bugs).
    // Charts stub (Phase 2) appears under the answer once a result exists.
    await expect(page.getByText('Charts', { exact: true }).first()).toBeVisible()
    // The AI follow-up suggestions stub (Phase 2) is labelled.
    await expect(
      page.getByText('AI follow-up suggestions', { exact: true }),
    ).toBeVisible()
    // At least one "Coming soon" badge is on the page.
    await expect(page.getByText(/Coming soon/i).first()).toBeVisible()
    // The library sidebar stub is labelled + disabled.
    await expect(page.getByText('Your library', { exact: true })).toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Save cleaned dataset' }),
    ).toBeDisabled()
    // The greyed "Daily total" header stub (Phase 5) is present and labelled.
    await expect(page.getByText(/Daily total/i)).toBeVisible()
  })
})
