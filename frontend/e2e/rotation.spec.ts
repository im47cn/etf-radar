import { test, expect } from '@playwright/test';

test.describe('Rotation page — trails overlay', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    const rotationLink = page.getByRole('link', { name: /轮动|Rotation/i });
    if (await rotationLink.count() > 0) {
      await rotationLink.first().click();
    }
  });

  test('shows trail-length slider and at least 1 theme bubble', async ({ page }) => {
    await expect(page.getByText(/主题轮动象限图/)).toBeVisible();
    await expect(page.getByText(/轨迹长度/)).toBeVisible();
    const symbols = page.locator('.recharts-scatter-symbol');
    await expect(symbols.first()).toBeVisible({ timeout: 10_000 });
  });

  test('clicking a bubble opens FocusedThemePanel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await expect(page.getByRole('region', { name: /主题详情面板/ })).toBeVisible();
  });

  test('ESC closes the focused panel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await expect(page.getByRole('region', { name: /主题详情面板/ })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('region', { name: /主题详情面板/ })).toHaveCount(0);
  });

  test('clicking close button (×) closes the panel', async ({ page }) => {
    await page.locator('.recharts-scatter-symbol').first().click({ force: true });
    await page.getByRole('button', { name: '关闭' }).click();
    await expect(page.getByRole('region', { name: /主题详情面板/ })).toHaveCount(0);
  });
});
