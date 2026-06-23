import { test, expect } from '@playwright/test';

/**
 * Phase 3 EventTimeline E2E。
 *
 * 完整流程（登录态 + 真实事件）需要 Supabase auth mock + user_events 注入，
 * 属 Phase 1 e2e 基建。本文件仅做"集成后 /portfolio 页未破"烟雾。
 *
 * 单测层面已覆盖：
 *   - eventDiff.test.ts (10 cases)
 *   - useEventsSnapshot.test.tsx (3 cases)
 *   - EventsProvider.test.tsx (1 case + Realtime mock)
 *   - usePortfolioEventDetection.test.ts (4 cases)
 *   - EventItem.test.tsx (6 cases)
 *   - EventTimeline.test.tsx (5 cases)
 *   - EventBadge.test.tsx (3 cases)
 */

test.describe('EventTimeline (smoke)', () => {
  test('/portfolio 集成 EventTimeline 后页面仍能渲染（匿名）', async ({ page }) => {
    await page.goto('/#/portfolio');
    const cardVisible = await Promise.race([
      page.getByText('持仓信号监控').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'login'),
      page.getByText('未配置 Supabase').waitFor({ state: 'visible', timeout: 5000 }).then(() => 'unconfig'),
    ]).catch(() => null);
    expect(cardVisible).toBeTruthy();
  });

  test.skip('登录态下 EventTimeline 折叠面板可见（待 Phase 1 e2e 基建）', () => {
    // 占位：需要 Supabase auth mock + 持仓 + 历史快照差异注入。
    // 完成后可解锁的断言：
    //   1. await page.getByRole('button', { name: /事件流/ }).click();
    //   2. await expect(page.getByText(/象限|强度|信号/)).toBeVisible();
    //   3. await page.getByRole('button', { name: /全部标为已读/ }).click();
    //   4. await expect(page.getByText(/事件流\(\d+\)/)).toBeVisible();  // 未读数清零
  });
});
