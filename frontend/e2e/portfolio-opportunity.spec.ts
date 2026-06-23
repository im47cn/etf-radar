import { test, expect } from '@playwright/test';

/**
 * Phase 2 OpportunityScanner E2E。
 *
 * 当前 e2e 基建仅覆盖匿名访问场景（参见 portfolio.spec.ts）——OpportunityScanner
 * 只在登录态 + 已有持仓的 populated 分支渲染，故完整跳转流程的 E2E 需要
 * Supabase auth mock + holdings 注入机制，属 Phase 1 e2e 基建范畴，不在本期落地。
 *
 * 单测层面已充分覆盖：
 *   - scanner.test.ts (8 cases)：过滤/排序/排除/边界
 *   - OpportunityCard.test.tsx (6 cases)：渲染/Link/L1+L2 立场
 *   - OpportunityScanner.test.tsx (7 cases)：折叠/展开/空态/计数
 *
 * 本文件仅做"集成后 /portfolio 页未破"的烟雾验证。
 */

test.describe('OpportunityScanner (smoke)', () => {
  test('/portfolio 集成 OpportunityScanner 后页面仍能渲染（匿名）', async ({ page }) => {
    await page.goto('/#/portfolio');
    // 匿名态下显示登录卡或未配置卡——只要任一就证明页面没有因 Phase 2 集成而崩
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
  });

  test.skip('登录态下信号扫描折叠面板可见 + 可点开（待 Phase 1 e2e 基建补完）', () => {
    // 占位：需要 Supabase auth mock + 持仓注入。
    // 完成后可解锁的断言：
    //   1. await page.getByRole('button', { name: /信号扫描/ }).click();
    //   2. await expect(page.getByText(/筛选条件/)).toBeVisible();
    //   3. await page.getByRole('link', { name: /查看详情/ }).first().click();
    //   4. await expect(page).toHaveURL(/[?&]theme=/);
  });
});
