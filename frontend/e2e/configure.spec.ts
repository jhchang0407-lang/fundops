import { test, expect } from '@playwright/test';

test.describe('Configure (Strategy Chat)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('page loads with chat interface', async ({ page }) => {
    // Should have an input for sending messages
    const inputs = page.locator('input[type="text"], textarea');
    const count = await inputs.count();
    expect(count).toBeGreaterThan(0);
  });

  test('agent chip strip renders', async ({ page }) => {
    // Should have agent chip buttons (ME, SC, TH, IC, etc.)
    const content = await page.locator('main, [class*="sidebar"], [class*="panel"]').first().textContent();
    const hasChips = content?.includes('ME') || content?.includes('SC') || content?.includes('TH');
    expect(hasChips).toBe(true);
  });

  test('send button exists', async ({ page }) => {
    const sendBtn = page.locator('button:has-text("Send"), button[type="submit"]');
    const count = await sendBtn.count();
    expect(count).toBeGreaterThan(0);
  });

  test('chip overlay opens on click', async ({ page }) => {
    // Find and click an agent chip
    const chips = page.locator('button:has-text("ME"), button:has-text("SC")');
    if (await chips.count() > 0) {
      await chips.first().click();
      await page.waitForTimeout(500);
      // Overlay should appear with more content
      const content = await page.locator('body').textContent();
      expect(content?.length).toBeGreaterThan(200);
    }
  });

  test('no console errors on load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    await page.waitForTimeout(2000);
    expect(errors).toHaveLength(0);
  });

  test('page does not crash', async ({ page }) => {
    const content = await page.locator('body').textContent();
    expect(content).not.toContain('Cannot read properties');
    expect(content).not.toContain('Application error');
  });
});
