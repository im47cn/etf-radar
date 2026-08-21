# SEPA 交易闭环 — 部署 Runbook（骨架）

> 面向运维/开发者的上线操作手册。数据层（M3）代码就绪；Actions 复盘闭环（M4）落地后补齐 §3。
> 契约与设计见 `docs/superpowers/specs/2026-08-20-sepa-trading-loop-spec.md`（§2.4 数据契约）。

## 架构一图

```
前端 GitHub Pages（/trading 页）
  ├─ TradesProvider ──► Supabase Postgres (RLS)
  │    trades（事件流）      trades          本人 FOR ALL
  │    trading_settings      trading_settings 本人 FOR ALL
  │    listReviews ────────► trade_reviews   本人 SELECT / Actions 写
  └─ 仓位计算器（前端事实性算数，无后端）
                                ▲
GitHub Actions (M4) ─service_role─┘  每晚 EOD 写 trade_reviews + ServerChan 推送
```

- **无自有后端服务器**：交易录入/持仓推导全在前端（trades 为 append-only 事件流，
  当前持仓由 `derivePositions()` 按 `(trade_date, created_at)` 升序回放推导）。
- 复盘评分（trade_reviews）只由 Actions 以 service_role key 写入（绕过 RLS），
  本人前端仅只读。

---

## 前置条件

- [ ] 已有 Supabase 项目（现有 OAuth 登录 / 001-005 迁移已在用）。
- [ ] 前端构建环境已有 `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`（复用现有配置）。

## 步骤

### 1. 建表（Supabase SQL Editor）

把 `backend/migrations/006_trades.sql` 全文粘进 **Supabase Dashboard → SQL Editor** 执行一次。
- 依赖 `001_user_holdings.sql` 里的 `set_updated_at()`（若没执行过 001 需先执行）。
- 建成 3 表 + RLS（可重复执行，幂等）：
  - `trades` — 本人 FOR ALL
  - `trade_reviews` — 本人仅 SELECT，无写策略（Actions service_role 写）
  - `trading_settings` — 本人 FOR ALL，参数默认 0.75 / 5 / 20 / 4

**验证**（SQL Editor 里）：
```sql
-- 应列出 3 张表，均 rls_enabled = true
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename like 'trade%';

-- 应恰好 4 条策略：trades_own(ALL) / trade_reviews_own_select(SELECT)
--                  / trading_settings_own(ALL)
select tablename, policyname, cmd from pg_policies
where schemaname = 'public' and tablename in ('trades','trade_reviews','trading_settings');
```

### 1b. 聚合统计物化表（007，复盘统计单一口径）

- [ ] `backend/migrations/007_review_aggregates.sql` 贴入 SQL Editor（review_aggregates 表，
      本人仅 SELECT，Actions service_role 每晚按用户覆写）。前端复盘 Tab 优先生读此快照。

### 2. Realtime（可选，推荐）

TradesProvider 已订阅 `trades` 表变更（多端录入实时刷新）。执行：
```sql
ALTER PUBLICATION supabase_realtime ADD TABLE trades;
```

### 3. Actions 复盘闭环（M4 已实现，部署时执行）

- [ ] `SUPABASE_SERVICE_ROLE_KEY` 配入 GitHub Secrets（Actions 写 trade_reviews 用）。
- [ ] `SERVERCHAN_SENDKEY` 配入 GitHub Secrets（owner dogfood 推送）。
- [x] trading-eod.yml 已扩展（pipeline + actions_main 两步，本地先 `--dry-run` 验证）。
- [ ] 验证：authenticated 身份直接 INSERT trade_reviews 应被 RLS 拒绝
  （仅 service_role 可写）。

### 4. 前端接线（二阶段）

- [ ] `App.tsx` 顶层挂 `<TradesProvider>`（与其他 Provider 并列）。
- [ ] `/trading` 持仓 Tab 消费 `useTrades()`：`positions` / `settings` / `addTrade`。
- [ ] 事实性文案审查：无"买入/卖出/清仓"指令词汇（合规立场 B）。

---

## 安全清单

- [ ] `service_role key` 只进 GitHub Secrets，绝不进前端/仓库。
- [ ] `trade_reviews` 无 authenticated 写策略（RLS 审查见
      `backend/tests/test_trading_migration.py`）。
- [ ] 免责声明与事实性文案（"价格进入买区"而非"建议买入"）。

## 回滚

- 撤下前端 `/trading` 持仓 Tab 入口 → 对用户不可见。
- 迁移为纯新增表，无副作用，可保留。
