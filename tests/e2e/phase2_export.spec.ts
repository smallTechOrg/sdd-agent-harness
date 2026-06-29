import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";
import os from "os";

function makeCsv(dir: string, name: string, content: string): string {
  const p = path.join(dir, name);
  fs.writeFileSync(p, content);
  return p;
}

test.describe("Phase 2 - Export CSV", () => {
  test("Export CSV button is visible after file upload", async ({ page }) => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-export-"));
    const csv1 = makeCsv(tmpDir, "sales.csv", "region,revenue\nWest,1000\nEast,2000\n");

    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("input[type=file]", { timeout: 10000 });
    await page.setInputFiles("input[type=file]", csv1);
    await page.waitForSelector("text=sales.csv", { timeout: 15000 });

    // Export CSV button should be visible and enabled (not the old stub)
    await expect(page.locator("text=Export CSV")).toBeVisible();
    // Old stub text should be gone
    await expect(page.locator("text=Export Data [Coming in Phase 2]")).not.toBeVisible();
  });

  test("end-to-end export downloads a CSV file after Q&A", async ({ page }) => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-export3-"));
    const csv1 = makeCsv(tmpDir, "orders.csv", "region,revenue\nWest,1000\nEast,2000\nNorth,1500\n");

    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("input[type=file]", { timeout: 10000 });
    await page.setInputFiles("input[type=file]", csv1);
    await page.waitForSelector("text=orders.csv", { timeout: 15000 });

    // Ask a question that returns a tabular result
    await page.fill("textarea", "Show me all rows as a table");
    await page.click("button:has-text('Send')");

    // Wait for assistant reply (real LLM — up to 45s)
    await expect(page.locator('[class*="justify-start"] p').first()).not.toBeEmpty({ timeout: 45000 });

    // Click Export CSV and wait for download
    const [download] = await Promise.all([
      page.waitForEvent("download", { timeout: 15000 }),
      page.click("text=Export CSV"),
    ]);

    expect(download.suggestedFilename()).toBe("result.csv");
    const downloadPath = await download.path();
    expect(downloadPath).toBeTruthy();
    const size = fs.statSync(downloadPath!).size;
    expect(size).toBeGreaterThan(0);
  });

  test("Export CSV button shows error when no Q&A result yet", async ({ page }) => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-export2-"));
    const csv1 = makeCsv(tmpDir, "data.csv", "x,y\n1,2\n3,4\n");

    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("input[type=file]", { timeout: 10000 });
    await page.setInputFiles("input[type=file]", csv1);
    await page.waitForSelector("text=data.csv", { timeout: 15000 });

    // Click Export CSV before asking any question
    await page.click("text=Export CSV");
    // Should show an error (no result yet)
    await expect(
      page.locator("text=No exportable result").or(page.locator("text=Export failed")).or(page.locator("text=no exportable"))
    ).toBeVisible({ timeout: 10000 });
  });
});
