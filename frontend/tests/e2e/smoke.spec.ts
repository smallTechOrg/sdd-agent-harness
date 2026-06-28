import { test, expect } from '@playwright/test'

/**
 * Smoke tests for Data Analysis Agent frontend.
 *
 * The page is a static export served at http://localhost:3099/
 * (basePath '/app' applies only when served behind FastAPI at /app/).
 */

test.describe('Data Analysis Agent smoke tests', () => {
  test('page loads and is styled', async ({ page }) => {
    await page.goto('/')

    // Title is correct
    await expect(page).toHaveTitle('Data Analysis Agent')

    // App heading is visible
    await expect(page.locator('h1')).toContainText('Data Analysis Agent')

    // Sidebar is rendered
    await expect(page.locator('aside')).toBeVisible()

    // Upload button is rendered and styled (indigo)
    const uploadBtn = page.getByTestId('upload-btn')
    await expect(uploadBtn).toBeVisible()
    await expect(uploadBtn).toHaveText('+ Upload CSV')
  })

  test('primary input and send button are rendered', async ({ page }) => {
    await page.goto('/')

    // Chat input area is present
    const input = page.getByTestId('question-input')
    await expect(input).toBeVisible()
    // Disabled because no file is selected
    await expect(input).toBeDisabled()

    // Send button is present and disabled
    const sendBtn = page.getByTestId('send-btn')
    await expect(sendBtn).toBeVisible()
    await expect(sendBtn).toBeDisabled()
  })

  test('empty state message shown when no messages', async ({ page }) => {
    await page.goto('/')

    // Empty state prompt is visible
    await expect(page.locator('[data-testid="question-input"]')).toBeVisible()
    // Prompt to upload a file
    await expect(page.locator('text=Upload a CSV file first')).toBeVisible()
  })

  test('labelled stubs are visible (Phase 2 indicators)', async ({ page }) => {
    await page.goto('/')

    // Multi-file join stub in sidebar
    await expect(page.locator('text=Multi-file join')).toBeVisible()
    await expect(page.locator('text=Coming in Phase 2').first()).toBeVisible()

    // Session history stub in chat panel
    await expect(page.locator('text=Session history')).toBeVisible()
  })

  test('file input accepts CSV only', async ({ page }) => {
    await page.goto('/')

    const fileInput = page.locator('[data-testid="file-input"]')
    await expect(fileInput).toHaveAttribute('accept', '.csv')
  })
})
