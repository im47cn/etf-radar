import { test, expect } from '@playwright/test';

test.describe('Portfolio (anonymous)', () => {
  test('Header 显示 交易 链接且无独立 持仓/自选 一级链接', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '交易', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: '持仓', exact: true })).toHaveCount(0);
    await expect(page.getByRole('link', { name: '自选', exact: true })).toHaveCount(0);
  });

  test('/portfolio 重定向到交易页主题持仓, 未登录显示登录卡或未配置卡', async ({ page }) => {
    await page.goto('/#/portfolio');
    // 登录卡可能是登录态、未配置态或匿名态——任一文本都接受
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
    // 旧路由重定向的机械 URL 断言
    await expect(page).toHaveURL(/#\/trading\?tab=holdings/);
  });

  test('现有 / 和 /rotation 路由仍工作', async ({ page }) => {
    await page.goto('/');
    // HashRouter 初次着陆 URL 不带 # 是正常的；只要导航后能进 #/rotation 即说明路由健康
    await page.getByRole('link', { name: '轮动', exact: true }).click();
    await expect(page).toHaveURL(/#\/rotation/);
  });
});
