import { test, expect } from '@playwright/test';

test.describe('Library', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/library');
  });

  test('renders three tabs', async ({ page }) => {
    await expect(page.locator('button:has-text("Browse")')).toBeVisible();
    await expect(page.locator('button:has-text("Memos")')).toBeVisible();
    await expect(page.locator('button:has-text("Ask the Library")')).toBeVisible();
  });

  test('Browse tab shows stats', async ({ page }) => {
    await expect(page.locator('text=Tickers')).toBeVisible();
    await expect(page.locator('text=Artifacts')).toBeVisible();
  });

  test('Browse search filters tickers', async ({ page }) => {
    await page.waitForTimeout(1000); // wait for data load
    const searchInput = page.locator('input').first();
    await searchInput.fill('META');
    await page.waitForTimeout(1500);
    const content = await page.locator('main').textContent();
    expect(content?.includes('META') || content?.includes('Meta')).toBe(true);
  });

  test('Browse search shows research data', async ({ page }) => {
    await page.waitForTimeout(1000);
    const searchInput = page.locator('input').first();
    await searchInput.fill('META');
    await page.waitForTimeout(1500);
    const content = await page.locator('main').textContent();
    expect(content?.length).toBeGreaterThan(100);
  });

  test('Memos tab shows memo list', async ({ page }) => {
    await page.locator('button:has-text("Memos")').click();
    await expect(page.locator('text=total memos')).toBeVisible();
  });

  test('Ask tab renders chat interface', async ({ page }) => {
    await page.locator('button.tab:has-text("Ask the Library")').click();
    await page.waitForTimeout(500);
    // Should show the Ask button (exact match, not the tab)
    await expect(page.locator('button.btn:has-text("Ask")')).toBeVisible();
  });

  test('Ask tab sends question and gets response', async ({ page }) => {
    await page.locator('button.tab:has-text("Ask the Library")').click();
    await page.waitForTimeout(500);
    const input = page.locator('input[placeholder*="Ask"]');
    await input.fill('What tickers have been researched?');

    const responsePromise = page.waitForResponse(resp =>
      resp.url().includes('/api/library/ask') && resp.status() === 200
    );
    await page.locator('button.btn:has-text("Ask")').click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
  });
});
