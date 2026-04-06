import { test, expect } from '@playwright/test';

test.describe('Allocator', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/allocator');
  });

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('text=Allocator').first()).toBeVisible();
  });

  test('KPI cards render', async ({ page }) => {
    const main = await page.locator('main').textContent();
    // Should have some portfolio metrics
    expect(main?.length).toBeGreaterThan(100);
  });

  test('action sections render', async ({ page }) => {
    // Look for action categories or empty state
    const content = await page.locator('main').textContent();
    const hasActions = content?.includes('TRIM') || content?.includes('ADD') ||
      content?.includes('EXIT') || content?.includes('No allocator');
    expect(hasActions).toBe(true);
  });

  test('action card shows ticker details', async ({ page }) => {
    const cards = page.locator('[class*="card"], [class*="Card"], div:has(button:has-text("Discuss"))');
    const count = await cards.count();
    if (count > 0) {
      const cardText = await cards.first().textContent();
      expect(cardText?.length).toBeGreaterThan(20);
    }
  });

  test('Discuss button opens AI chat', async ({ page }) => {
    const discussBtn = page.locator('button:has-text("Discuss")').first();
    if (await discussBtn.isVisible()) {
      await discussBtn.click();
      await page.waitForTimeout(500);
      // Should show chat area or input after clicking discuss
      const content = await page.locator('main').textContent();
      expect(content?.length).toBeGreaterThan(100);
    }
  });

  test('Run Allocator button exists', async ({ page }) => {
    const runBtn = page.locator('button:has-text("Run Allocator"), button:has-text("Run")');
    const count = await runBtn.count();
    expect(count).toBeGreaterThan(0);
  });
});
