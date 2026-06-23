import { expect, test } from '@playwright/test';

test('navigate from rotation focused panel to stocks page', async ({ page }) => {
  await page.goto('/#/rotation');

  // 等待轮动图加载：至少一个 recharts 散点符号出现
  await page.locator('.recharts-scatter-symbol').first().waitFor({ timeout: 15_000 });

  // 点击第一个主题气泡
  await page.locator('.recharts-scatter-symbol').first().click({ force: true });

  // FocusedThemePanel 出现
  const panel = page.getByRole('region', { name: /主题详情面板/ });
  await expect(panel).toBeVisible();

  // 点击"查看主题成分股"按钮
  await panel.getByRole('button', { name: /查看主题成分股/ }).click();

  // 跳转到 stocks 子页面
  await expect(page).toHaveURL(/\/theme\/[^/]+\/stocks/);

  // 表格或空态二选一显示
  const hasTable = await page.getByRole('table').count();
  const hasEmpty = await page.getByRole('status').count();
  expect(hasTable + hasEmpty).toBeGreaterThan(0);
});
