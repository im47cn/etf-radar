import { test, expect } from '@playwright/test';

test.describe('Portfolio (anonymous)', () => {
  test('Header 显示 我的持仓 链接', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '我的持仓' })).toBeVisible();
  });

  test('/portfolio 未登录显示登录卡或未配置卡', async ({ page }) => {
    await page.goto('/#/portfolio');
    // 登录卡可能是登录态、未配置态或匿名态——任一文本都接受
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
  });

  test('现有 / 和 /rotation 路由仍工作', async ({ page }) => {
    await page.goto('/');
    // HashRouter 初次着陆 URL 不带 # 是正常的；只要导航后能进 #/rotation 即说明路由健康
    await page.getByRole('link', { name: '主题轮动' }).click();
    await expect(page).toHaveURL(/#\/rotation/);
  });
});
