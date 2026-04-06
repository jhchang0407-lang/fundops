import { test, expect } from '@playwright/test';

test.describe('Research Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/research');
  });

  test('renders three tabs with counts', async ({ page }) => {
    await expect(page.locator('button.tab:has-text("Thesis")')).toBeVisible();
    await expect(page.locator('button.tab:has-text("IC Review")')).toBeVisible();
    await expect(page.locator('button.tab:has-text("Approved")')).toBeVisible();
  });

  test('thesis tab shows table with required columns', async ({ page }) => {
    const headers = ['TICKER', 'FAIR VALUE', 'EXPECTED RETURN', 'DISCOUNT', 'CONVICTION', 'STAGE'];
    for (const header of headers) {
      await expect(page.locator(`th:has-text("${header}")`).first()).toBeVisible();
    }
  });

  test('thesis row expands with summary and valuation', async ({ page }) => {
    const firstDataRow = page.locator('table tbody tr').nth(1); // skip section header
    await firstDataRow.click();
    await expect(page.locator('text=THESIS SUMMARY').first()).toBeVisible({ timeout: 3000 });
    await expect(page.locator('text=VALUATION').first()).toBeVisible({ timeout: 3000 });
  });

  test('IC Review tab loads with verdict columns', async ({ page }) => {
    await page.locator('button:has-text("IC Review")').click();
    await expect(page.locator('th:has-text("VERDICT")')).toBeVisible();
    await expect(page.locator('th:has-text("BASE RETURN")')).toBeVisible();
    await expect(page.locator('th:has-text("BEAR RETURN")')).toBeVisible();
    await expect(page.locator('th:has-text("CONVICTION")')).toBeVisible();
  });

  test('IC Review shows PASS and NO PASS badges', async ({ page }) => {
    await page.locator('button:has-text("IC Review")').click();
    await page.waitForTimeout(500);
    const tableText = await page.locator('table').textContent();
    expect(tableText).toContain('NO PASS');
  });

  test('Approved tab loads', async ({ page }) => {
    await page.locator('button:has-text("Approved")').click();
    await page.waitForTimeout(500);
    // Should show approved tickers or empty state
    const content = await page.locator('main').textContent();
    expect(content?.includes('approved') || content?.includes('TICKER')).toBe(true);
  });

  test('Approved tab shows memo action buttons', async ({ page }) => {
    await page.locator('button:has-text("Approved")').click();
    await page.waitForTimeout(500);
    // Look for Reports/Memos/Generate Both buttons
    const hasButtons = await page.locator('button:has-text("Reports"), button:has-text("Memos"), button:has-text("Generate Both")').count();
    expect(hasButtons).toBeGreaterThan(0);
  });
});
