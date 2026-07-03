# 执行计划 — 会员订阅 MVP

按依赖顺序分 5 个阶段。每阶段末为验证/评审点（review gate）。无 git commit 由实现子代理执行（Trellis 约定）。

## 阶段 0：外部准备（人工，非代码，可并行）
- [ ] 在爱发电创建账号，建立「月度 ¥6」「年度 ¥58」两个订阅方案，记录各自 `plan_id` 与订阅链接。
- [ ] 获取 afdian `token` 与 `user_id`，配置 afdian webhook 回调 URL（指向 Edge Function）。
- [ ] Supabase 项目获取 `service_role key`，准备 Edge Function secrets。
- **Gate**：拿到 plan_id / token / user_id / 订阅链接，方可联调阶段 3。前面阶段 1-2、4 不阻塞。

## 阶段 1：数据层（迁移 + RLS + RPC）
- [ ] 新增 `backend/migrations/003_membership.sql`：`subscriptions`、`bind_codes`、`watchlist`、`webhook_events` 四表 + 索引 + `set_updated_at` 触发器。
- [ ] RLS 策略：`subscriptions` 仅本人 SELECT；`bind_codes` 仅本人 SELECT；`watchlist` 本人 FOR ALL；`webhook_events` 无 authenticated 策略（仅 service_role）。
- [ ] `SECURITY DEFINER` 函数：`issue_bind_code()`（复用未消费码或新建）、`add_watchlist(item_type,item_key)`（内校验订阅有效性，非会员 RAISE EXCEPTION）。
- **验证**：在 Supabase SQL Editor 执行迁移无错；手动 SQL 验证 RLS（切换角色查他人数据应为空）、`add_watchlist` 非会员应报错。
- **Gate**：数据层契约确认（表结构 / RPC 签名）后再动前端。

## 阶段 2：前端数据 hook（依赖阶段 1 契约）
- [ ] `src/lib/subscription/`：`useSubscription`（三态 + 到期回落判定）+ 类型定义。
- [ ] `src/lib/watchlist/`：`useWatchlist`（list/add via RPC/remove）+ 类型。
- [ ] 单测：仿 `src/lib/holdings/__tests__/useEtfHoldings.test.ts`，mock supabase，覆盖三态、到期回落、非会员 add 报错。
- **验证**：`npx vitest run src/lib/subscription src/lib/watchlist 2>&1 | tail -20` 全绿。

## 阶段 3：Edge Function（依赖阶段 0 密钥 + 阶段 1 表）
- [ ] `supabase/functions/afdian-webhook/index.ts`（Deno）：验签 → 幂等（out_trade_no）→ 解析 remark 绑定码 → 周期计算（plan_id→monthly/yearly）→ upsert subscriptions + consume bind_code + 写 webhook_events。
- [ ] 异常路径全部落 `webhook_events`（验签失败/无绑定码/未匹配用户）。
- [ ] Deno 单测：mock afdian payload，覆盖验签通过/失败、幂等重放、绑定码缺失/无效、月/年周期、续订叠加。
- **验证**：`deno test` 全绿；本地用 afdian 文档示例 payload 跑通；部署后用爱发电真实小额订单端到端联调一次。
- **Gate**：真实订单能激活会员 → 收款闭环成立。

## 阶段 4：UI（依赖阶段 2 hook，可与阶段 3 并行）
- [ ] `MemberGate` 组件（仿 `AuthGate`）：非会员 → 升级引导，会员 → children。
- [ ] `MembershipPage`（`/membership`）：AuthGate 包裹；权益、月/年定价卡、绑定码块（调 `issue_bind_code`）、爱发电按钮、订阅状态。
- [ ] 自选：雷达/主题页「加自选」按钮（会员可点）；「我的自选」视图（MemberGate 包裹，展示自选项当前状态，复用 themes/etfs 数据）。
- [ ] 免责声明组件；全文案审查无操作动词。
- [ ] 路由注册（HashRouter）+ 导航入口。
- **验证**：`npx vitest run 2>&1 | tail -10` 全绿；本地手动走查未登录/登录未订阅/会员三态。

## 阶段 5：整合验收与收尾
- [ ] 逐条核对 prd.md Acceptance Criteria。
- [ ] 前端全量测试 + 后端全量测试全绿（见 CLAUDE.md 命令）。
- [ ] 合规文案终审（禁操作动词 + 免责声明到位）。
- [ ] `trellis-check` → `trellis-update-spec` → 提交（Phase 3.4）。

## 验证命令速查
- 前端定向：`cd frontend && npx vitest run src/lib/subscription src/lib/watchlist 2>&1 | tail -20`
- 前端全量：`cd frontend && npx vitest run 2>&1 | grep -E "^(Test Files|Tests)" | tail -5`
- 后端全量：`cd backend && uv run --all-extras pytest 2>&1 | tail -15`
- Edge Function：`cd supabase/functions/afdian-webhook && deno test 2>&1 | tail -20`

## 回滚点
- 每阶段独立可回滚：撤路由/导航即对用户隐藏（阶段 4）；Edge Function 可单独下线（阶段 3）；迁移为纯新增无副作用（阶段 1）。
