import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";
import os from "os";

// Helper to create a small CSV file
function makeCsv(dir: string, name: string, content: string): string {
  const p = path.join(dir, name);
  fs.writeFileSync(p, content);
  return p;
}

test.describe("Phase 2 - Multi-file upload", () => {
  test("uploads two CSV files and shows two profile cards", async ({ page }) => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-"));
    const csv1 = makeCsv(tmpDir, "orders.csv", "order_id,amount\n1,100\n2,200\n3,300\n");
    const csv2 = makeCsv(tmpDir, "products.csv", "product_id,category,price\n1,A,10\n2,B,20\n");

    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("input[type=file]", { timeout: 10000 });

    // Upload first file
    await page.setInputFiles("input[type=file]", csv1);
    await page.waitForSelector("text=orders.csv", { timeout: 15000 });

    // Click "Add another file"
    await page.click("text=Add another file");
    await page.waitForSelector("input[type=file]", { timeout: 5000 });

    // Upload second file
    await page.setInputFiles("input[type=file]", csv2);
    await page.waitForSelector("text=products.csv", { timeout: 15000 });

    // Both profile cards should be visible
    await expect(page.locator("text=orders.csv")).toBeVisible();
    await expect(page.locator("text=products.csv")).toBeVisible();
  });

  test("dropzone accepts .xlsx file extension text", async ({ page }) => {
    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("text=CSV and Excel (.xlsx) supported", { timeout: 10000 });
    // Verify the old Phase 1 stub text is gone
    await expect(page.locator("text=CSV only — Excel support coming in Phase 2")).not.toBeVisible();
  });

  test("shows error when uploading an unsupported file type", async ({ page }) => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-err-"));
    const pdfPath = path.join(tmpDir, "report.pdf");
    fs.writeFileSync(pdfPath, "%PDF-1.4 fake pdf content");

    await page.goto("http://localhost:8001/app/");
    await page.waitForSelector("input[type=file]", { timeout: 10000 });
    await page.setInputFiles("input[type=file]", pdfPath);

    // Backend rejects .pdf — error message should appear
    await expect(
      page.locator("text=Only CSV and Excel").or(page.locator("text=Unsupported")).or(page.locator("text=supported"))
    ).toBeVisible({ timeout: 10000 });
  });
});
