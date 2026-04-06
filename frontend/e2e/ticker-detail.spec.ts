import { test, expect } from '@playwright/test';

test.describe('Ticker Detail', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/ticker/AAPL');
  });

  test('page loads with ticker name', async ({ page }) => {
    await expect(page.locator('text=AAPL').first()).toBeVisible();
  });

  test('tabs render', async ({ page }) => {
    await expect(page.locator('button:has-text("Overview")').first()).toBeVisible();
    await expect(page.locator('button:has-text("Research")').first()).toBeVisible();
  });

  test('Overview shows key metrics', async ({ page }) => {
    const content = await page.locator('main').textContent();
    // Should contain financial data
    expect(content?.length).toBeGreaterThan(100);
  });

  test('Research tab loads', async ({ page }) => {
    await page.locator('button:has-text("Research")').first().click();
    await page.waitForTimeout(500);
    const content = await page.locator('main').textContent();
    expect(content?.length).toBeGreaterThan(50);
  });

  test('Health tab loads', async ({ page }) => {
    const healthBtn = page.locator('button:has-text("Health")').first();
    if (await healthBtn.isVisible()) {
      await healthBtn.click();
      await page.waitForTimeout(500);
      const content = await page.locator('main').textContent();
      expect(content?.length).toBeGreaterThan(50);
    }
  });

  test('Evidence tab loads', async ({ page }) => {
    const evidenceBtn = page.locator('button:has-text("Evidence")').first();
    if (await evidenceBtn.isVisible()) {
      await evidenceBtn.click();
      await page.waitForTimeout(500);
      const content = await page.locator('main').textContent();
      expect(content?.length).toBeGreaterThan(50);
    }
  });

  test('unknown ticker shows graceful state', async ({ page }) => {
    await page.goto('/ticker/ZZZZZZZ');
    await page.waitForTimeout(2000);
    // Should not crash — either empty state or error message
    const content = await page.locator('body').textContent();
    expect(content).not.toContain('Cannot read properties');
    expect(content).not.toContain('Application error');
  });

  test('no NaN in metrics', async ({ page }) => {
    const content = await page.locator('main').textContent();
    expect(content).not.toContain('NaN');
  });
});
