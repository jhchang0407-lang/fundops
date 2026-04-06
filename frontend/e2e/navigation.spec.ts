import { test, expect } from '@playwright/test';

test.describe('Navigation Shell', () => {
  test('sidebar renders with all nav items', async ({ page }) => {
    await page.goto('/');
    const navItems = ['Chat', 'Dashboard', 'Screener', 'Research', 'Portfolio', 'Library', 'Allocator', 'Settings'];
    for (const item of navItems) {
      await expect(page.locator(`a:has-text("${item}")`).first()).toBeVisible();
    }
  });

  test('navigate to each page without crash', async ({ page }) => {
    const routes = [
      { nav: 'Dashboard', heading: 'Dashboard' },
      { nav: 'Screener', heading: 'Screener' },
      { nav: 'Research', heading: 'Thesis + IC Pipeline' },
      { nav: 'Portfolio', heading: 'Held Positions' },
      { nav: 'Library', heading: 'Browse' },
      { nav: 'Allocator', heading: 'Position Recommendations' },
      { nav: 'Settings', heading: 'Data Sources' },
    ];

    await page.goto('/dashboard');
    for (const route of routes) {
      await page.locator(`a:has-text("${route.nav}")`).first().click();
      await expect(page.locator(`text=${route.heading}`).first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('Run Pipeline button visible in sidebar', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('button:has-text("Run Pipeline")')).toBeVisible();
  });

  test('/thesis redirects to /research', async ({ page }) => {
    await page.goto('/thesis');
    await expect(page).toHaveURL(/\/research/);
  });

  test('/ic-review redirects to /research', async ({ page }) => {
    await page.goto('/ic-review');
    await expect(page).toHaveURL(/\/research/);
  });

  test('/nonexistent does not crash', async ({ page }) => {
    await page.goto('/nonexistent');
    // Should not show error, page should render
    const content = await page.locator('body').textContent();
    expect(content).not.toContain('Application error');
  });
});
