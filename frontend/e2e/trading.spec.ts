import { test, expect } from '@playwright/test';

/**
 * /trading 页 E2E (smoke)。
 *
 * 覆盖: 路由可达 + 一级导航链接 + 匿名门禁形态。
 * - 环境 Tab 为免费内容: trading.json 未产出时降级为「暂无交易环境数据」占位, 同样证明页面未崩。
 * - 信号/持仓/复盘 Tab 会员门: 匿名态显示登录卡 (HeroLogin) 或未配置卡 (本地无 Supabase env)。
 * 登录态 + member 态的完整表格渲染由单测 (tradingPage.test.tsx) 覆盖;
 * e2e 登录基建 (Supabase auth mock) 属后续基建, 参见 portfolio-events.spec.ts 同款说明。
 */

test.describe('Trading page (anonymous)', () => {
  test('Header 显示 交易 链接', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('link', { name: '交易', exact: true })).toBeVisible();
  });

  test('#/trading 路由可达, 环境 Tab 免费可见', async ({ page }) => {
    await page.goto('/#/trading');
    await expect(page.getByRole('heading', { name: '交易' })).toBeVisible();
    // 环境 Tab 免费: 数据产出则显示档位徽标, 未产出则显示降级占位.
    // 锚定正则避免规则说明文案 ("其余为中性") 的子串误匹配.
    const envVisible = await page
      .getByText(/^(进攻|中性|防守|数据缺失|暂无交易环境数据)$/)
      .first()
      .waitFor({ state: 'visible', timeout: 8000 })
      .then(() => true)
      .catch(() => false);
    expect(envVisible).toBe(true);
  });

  test('匿名点信号 Tab 显示登录卡或未配置卡', async ({ page }) => {
    await page.goto('/#/trading');
    await page.getByRole('tab', { name: /信号/ }).click();
    const gateVisible = await Promise.race([
      page.getByText('交易信号跟踪').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(gateVisible).toBeTruthy();
  });

  test('匿名点持仓 Tab 显示门控卡', async ({ page }) => {
    await page.goto('/#/trading');
    await page.getByRole('tab', { name: '持仓', exact: true }).click();
    const gateVisible = await Promise.race([
      page.getByText('持仓管理').first().waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(gateVisible).toBeTruthy();
  });

  test('交易页含 自选 与 主题持仓 Tab, 匿名点主题持仓显示门控卡', async ({ page }) => {
    await page.goto('/#/trading');
    await expect(page.getByRole('tab', { name: '自选', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: '主题持仓', exact: true })).toBeVisible();
    await page.getByRole('tab', { name: '主题持仓', exact: true }).click();
    // 主题持仓为 auth 开放功能: 匿名态显示登录卡 (HeroLogin copy 'portfolio') 或未配置卡
    const gateVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(gateVisible).toBeTruthy();
  });
});
