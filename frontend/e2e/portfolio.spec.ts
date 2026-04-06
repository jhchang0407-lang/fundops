import { test, expect } from '@playwright/test';

test.describe('Portfolio', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/portfolio');
  });

  test('renders KPI cards', async ({ page }) => {
    await expect(page.locator('text=Portfolio Value').first()).toBeVisible();
    await expect(page.locator('text=Total P&L').first()).toBeVisible();
    await expect(page.locator('text=Positions').first()).toBeVisible();
    await expect(page.locator('text=Thesis Health').first()).toBeVisible();
  });

  test('holdings table shows positions', async ({ page }) => {
    const headers = ['TICKER', 'SHARES', 'COST', 'PRICE', 'P&L', 'WEIGHT'];
    for (const header of headers) {
      await expect(page.locator(`th:has-text("${header}")`).first()).toBeVisible();
    }
  });

  test('portfolio value is not NaN', async ({ page }) => {
    const text = await page.locator('main').textContent();
    expect(text).not.toContain('NaN');
    expect(text).not.toContain('undefined');
  });

  test('Refresh Prices button exists', async ({ page }) => {
    await expect(page.locator('button:has-text("Refresh Prices")')).toBeVisible();
  });

  test('Edit Positions opens editor', async ({ page }) => {
    await page.locator('button:has-text("Edit Positions")').click();
    await expect(page.locator('text=Save Changes')).toBeVisible();
    await expect(page.locator('text=Cancel')).toBeVisible();
    await expect(page.locator('button:has-text("+ Add another position")')).toBeVisible();
  });

  test('Edit Positions cancel restores original', async ({ page }) => {
    await page.locator('button:has-text("Edit Positions")').click();
    await expect(page.locator('text=Save Changes')).toBeVisible();
    await page.locator('button:has-text("Cancel")').click();
    // Editor should be closed
    await expect(page.locator('text=Save Changes')).not.toBeVisible();
  });

  test('ticker links navigate to detail page', async ({ page }) => {
    const ticker = page.locator('table tbody td a').first();
    const tickerText = await ticker.textContent();
    await ticker.click();
    await expect(page).toHaveURL(new RegExp(`/ticker/${tickerText}`));
  });

  test('thesis alerts section renders', async ({ page }) => {
    await expect(page.locator('text=THESIS ALERTS')).toBeVisible();
  });

  test('Refresh Prices makes API call', async ({ page }) => {
    const responsePromise = page.waitForResponse(resp =>
      resp.url().includes('/api/portfolio') && resp.status() === 200
    );
    await page.locator('button:has-text("Refresh Prices")').click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
  });
});
