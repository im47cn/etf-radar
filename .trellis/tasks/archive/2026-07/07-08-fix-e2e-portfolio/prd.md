# 修前端 e2e portfolio.spec 失败

## Goal
修复 CI 长期 red 的两个 e2e 用例,恢复 e2e 绿灯(它阻塞/污染所有 PR 的 CI 判定)。

## 根因(systematic-debugging 定位)
**陈旧测试,非产品 bug。** 导航栏 `RadarTabs.tsx` 的标签早前被**有意缩短**(`温度/轮动/雷达/持仓/自选/会员`,修复移动端 6 tab 换行,见记忆 obs 11671/11672,已上线),但 `e2e/portfolio.spec.ts` 仍断言旧长名:
- `portfolio.spec.ts:6` 期望 `link name '我的持仓'` → 现为 `持仓` → `element not found`。
- `portfolio.spec.ts:22` 期望 `link name '主题轮动'` → 现为 `轮动` → 点击超时 30s。

复现回路:`cd frontend && npx playwright test e2e/portfolio.spec.ts --project=chromium`(修前 2 fail,修后 3 pass / 1.4s)。

## 修复
`e2e/portfolio.spec.ts`:`我的持仓`→`持仓`、`主题轮动`→`轮动`,并加 `exact: true` 避免误配页面正文(如"我的持仓（N 只）"标题、"主题轮动象限图")。

## 排查范围(确认无其他残留)
`主题轮动象限图`(RotationPage 标题)、`我的持仓（N 只）`(HoldingsList 标题)等均为**页面文本非导航链接**,合法保留;`rotation.spec.ts:6` 已用正则稳健匹配。仅 portfolio.spec 一处陈旧。

## Acceptance Criteria
- [x] `npx playwright test e2e/portfolio.spec.ts --project=chromium` 全绿(3 passed)。
- [x] CI e2e job 转绿(PR #25:backend/frontend/e2e/CodeRabbit/Sourcery 全 SUCCESS)。

## 附带修复
推送时发现并行会话的 C2 `AsOfBadge.tsx` 触发 `react-refresh/only-export-components` 打挂 frontend job(致 e2e 被 skip)。拆 `asOfLabel`+`todayBjt` 到独立 `asOfLabel.ts` 修复(commit 与本任务同批)。

## 复盘 / 预防
- 改导航标签时应同步更新耦合的 e2e 断言(同一提交内)。
- 稳健写法:nav 链接断言优先用正则(如 `/轮动|Rotation/i`,rotation.spec 已示范),而非精确长字符串,降低文案微调导致的脆性。
