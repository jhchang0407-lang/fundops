import { test, expect } from '@playwright/test';

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings');
  });

  test('page loads with tabs', async ({ page }) => {
    await expect(page.locator('button:has-text("Data Sources")').first()).toBeVisible();
    await expect(page.locator('button:has-text("AI Model")').first()).toBeVisible();
    await expect(page.locator('button:has-text("Schedule")').first()).toBeVisible();
    await expect(page.locator('button:has-text("System")').first()).toBeVisible();
  });

  test('Data Sources tab shows connectors', async ({ page }) => {
    await expect(page.locator('text=Yahoo Finance').first()).toBeVisible();
    await expect(page.locator('text=SEC EDGAR').first()).toBeVisible();
  });

  test('Data Sources shows connection status', async ({ page }) => {
    const content = await page.locator('main').textContent();
    const hasStatus = content?.includes('Connected') || content?.includes('configured');
    expect(hasStatus).toBe(true);
  });

  test('AI Model tab loads', async ({ page }) => {
    await page.locator('button:has-text("AI Model")').first().click();
    await page.waitForTimeout(500);
    const content = await page.locator('main').textContent();
    // Should show provider options
    const hasProvider = content?.includes('OpenAI') || content?.includes('Provider') || content?.includes('Model');
    expect(hasProvider).toBe(true);
  });

  test('Schedule tab shows agent cards', async ({ page }) => {
    await page.locator('button:has-text("Schedule")').first().click();
    await page.waitForTimeout(500);
    const content = await page.locator('main').textContent();
    const hasAgents = content?.includes('Screener') || content?.includes('screener') ||
      content?.includes('Daily') || content?.includes('Manual');
    expect(hasAgents).toBe(true);
  });

  test('System tab loads', async ({ page }) => {
    await page.locator('button:has-text("System")').first().click();
    await page.waitForTimeout(500);
    const content = await page.locator('main').textContent();
    const hasSystem = content?.includes('Database') || content?.includes('Export') ||
      content?.includes('Reset') || content?.includes('sqlite');
    expect(hasSystem).toBe(true);
  });

  test('Test Connection buttons exist', async ({ page }) => {
    const testBtns = page.locator('button:has-text("Test")');
    const count = await testBtns.count();
    expect(count).toBeGreaterThan(0);
  });
});
