import { test, expect } from '@playwright/test';

test.describe('Screener', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/screener');
  });

  test('page loads with stock table', async ({ page }) => {
    await expect(page.locator('text=Screener').first()).toBeVisible();
    await expect(page.locator('table').first()).toBeVisible();
  });

  test('table has required columns', async ({ page }) => {
    const headers = ['TICKER', 'COMPANY', 'SECTOR', 'PRICE', 'RETURN', 'ACTIONS'];
    for (const header of headers) {
      await expect(page.locator(`th:has-text("${header}")`).first()).toBeVisible();
    }
  });

  test('stock rows render with data', async ({ page }) => {
    const rows = page.locator('table tbody tr');
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
  });

  test('ticker links navigate to ticker detail', async ({ page }) => {
    const firstTicker = page.locator('table tbody tr td a').first();
    const ticker = await firstTicker.textContent();
    await firstTicker.click();
    await expect(page).toHaveURL(new RegExp(`/ticker/${ticker}`));
  });

  test('row expand shows details', async ({ page }) => {
    const firstRow = page.locator('table tbody tr').first();
    await firstRow.click();
    // Expanded content should appear
    await page.waitForTimeout(500);
    const expandedContent = page.locator('table tbody tr').nth(1);
    const text = await expandedContent.textContent();
    expect(text?.length).toBeGreaterThan(50);
  });

  test('Run Screener button visible', async ({ page }) => {
    await expect(page.locator('button:has-text("Run Screener")')).toBeVisible();
  });

  test('promote and dismiss buttons exist on rows', async ({ page }) => {
    // Action buttons use ⊕ (promote) and ⊖ (dismiss) symbols with title attributes
    const actionBtns = page.locator('button[title="Promote to thesis"], button[title="Dismiss"]');
    const count = await actionBtns.count();
    expect(count).toBeGreaterThan(0);
  });
});
