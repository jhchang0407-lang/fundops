import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard');
  });

  test('renders KPI cards', async ({ page }) => {
    await expect(page.locator('text=Portfolio').first()).toBeVisible();
    await expect(page.locator('text=Daily P&L').first()).toBeVisible();
    await expect(page.locator('text=Agent Runs').first()).toBeVisible();
    await expect(page.locator('text=Pipeline').first()).toBeVisible();
    await expect(page.locator('text=Status').first()).toBeVisible();
  });

  test('portfolio value is not NaN', async ({ page }) => {
    const text = await page.locator('main').textContent();
    expect(text).not.toContain('NaN');
  });

  test('recent activity section renders', async ({ page }) => {
    await expect(page.locator('text=RECENT ACTIVITY')).toBeVisible();
  });

  test('holdings table renders', async ({ page }) => {
    const holdingsSection = page.locator('text=HOLDINGS').first();
    await expect(holdingsSection).toBeVisible();
  });

  test('schedules table renders', async ({ page }) => {
    await expect(page.locator('text=SCHEDULES')).toBeVisible();
  });

  test('agent status sidebar renders', async ({ page }) => {
    const content = await page.locator('main').textContent();
    const hasAgentStatus = content?.includes('Agent') || content?.includes('agent') || content?.includes('idle');
    expect(hasAgentStatus).toBe(true);
  });

  test('no console errors on load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors).toHaveLength(0);
  });
});
