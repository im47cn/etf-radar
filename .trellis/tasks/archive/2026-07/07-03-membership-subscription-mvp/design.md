# 技术设计 — 会员订阅 MVP

## 1. 架构总览

```
GitHub Actions (Python pipeline)          爱发电 afdian
   产出公开 JSON (data/latest 等)             用户订阅付款 (¥6/月 · ¥58/年)
        │                                        │ webhook POST
        │                                        ▼
        │                        Supabase Edge Function「afdian-webhook」
        │                        验签 → 解析留言绑定码 → upsert subscriptions
        │                                        │
        ▼                                        ▼
   前端 (GitHub Pages / React + HashRouter)   Supabase Postgres
   ├─ useSubscription() ── 读 subscriptions ──►  ├─ subscriptions (RLS: 本人只读)
   ├─ useWatchlist()   ── 读写 watchlist ─────►  ├─ watchlist      (RLS: 本人读写)
   └─ 升级页/自选视图                            └─ bind_codes     (RLS: 本人读, 服务端写)
```

设计原则：MVP **纯 serverless**，不引入自有后端。唯一服务端逻辑是一个 Supabase Edge Function（webhook 接收器），其余靠 Postgres + RLS。

## 2. 数据模型（新增迁移 `backend/migrations/003_membership.sql`）

沿用现有约定：`auth.users(id)` 外键、`set_updated_at()` 触发器、RLS `auth.uid()`。

### 2.1 `subscriptions`
```
id           uuid PK default gen_random_uuid()
user_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE, UNIQUE
plan         text NOT NULL CHECK (plan IN ('monthly','yearly'))
status       text NOT NULL DEFAULT 'inactive' CHECK (status IN ('active','inactive','expired'))
current_period_end  timestamptz          -- 到期时间；status 有效性以此为准
source       text NOT NULL DEFAULT 'afdian'
afdian_trade_no     text                 -- 最近一笔订单号，幂等去重用
created_at / updated_at  timestamptz (触发器维护)
```
- RLS：`SELECT` 仅本人（`user_id = auth.uid()`）。**无 INSERT/UPDATE/DELETE 策略给 authenticated**——写入只由 Edge Function 用 service_role key 完成（绕过 RLS），杜绝前端伪造会员。

### 2.2 `bind_codes`（账号打通）
```
id         uuid PK
user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE
code       text NOT NULL UNIQUE       -- 短码, 如 8 位 base32
consumed   boolean NOT NULL DEFAULT false
created_at timestamptz
```
- RLS：`SELECT` 仅本人。生成通过 Postgres `RPC`（`SECURITY DEFINER` 函数 `issue_bind_code()`）：若本人存在未 consumed 的有效码则返回该码，否则生成新码。避免前端直接 INSERT。

### 2.3 `watchlist`
```
id         uuid PK
user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE
item_type  text NOT NULL CHECK (item_type IN ('theme','etf'))
item_key   text NOT NULL              -- 主题 id 或 ETF code
created_at timestamptz
UNIQUE (user_id, item_type, item_key)
```
- RLS：`FOR ALL` 本人读写（同 `user_holdings` 的 `holdings_own` 策略）。
- **注意**：RLS 只保证「本人数据隔离」，不保证「仅会员可写」。会员校验放在 Edge Function 侧的写路径 **或** 前端软门控 + 一个 `SECURITY DEFINER` 的 `add_watchlist()` RPC 内校验 `subscriptions.status`。MVP 采用后者：`add_watchlist` RPC 内先查订阅有效性，非会员抛错。这样「仅会员可用自选」成为服务端硬约束。

## 3. 收款闭环（爱发电 → Supabase）

### 3.1 绑定码流程
1. 用户登录后进入升级页 → 前端调 `issue_bind_code()` RPC 得到 `code`。
2. 页面展示：定价、爱发电订阅链接（月/年两档）、以及「下单时请在留言填写此绑定码：`XXXXXXXX`」。
3. 用户在爱发电完成订阅，在订单留言填入绑定码。

### 3.2 Edge Function `afdian-webhook`（`supabase/functions/afdian-webhook/`）
- 部署为 Supabase Edge Function（Deno），用 **service_role key** 写库。
- **验真方式（重要修正）**：afdian Webhook 回调 **payload 不含 sign 字段，无法做签名比对**。正确做法是拿回调的 `out_trade_no` **反向调 afdian `query-order` API 核实订单真实存在且已支付**，并以 API 返回的订单为权威数据源（防伪造 webhook）。
- 步骤：
  1. **解析**：读 `data.order.out_trade_no`；ping/test 回调直接返回 `{ec:200}`。
  2. **幂等**：若 `subscriptions.afdian_trade_no` 已等于该单 → 直接返回 `{ec:200}`（在核实前短路，省一次 API 调用）。
  3. **核实**：POST `https://afdian.net/api/open/query-order`，body `{user_id, params:'{"out_trade_no":"…"}', ts, sign}`，其中 `sign = md5(token + "params"+params + "ts"+ts + "user_id"+user_id)`（按 key 升序拼接、小写 md5）。校验 `ec===200` 且 list 中匹配到该单且 `status===2`（已支付）。失败 → `webhook_events(outcome='order_verify_failed')` → 返回 200。
  4. **解析绑定码**：从**权威订单** `remark` 提取绑定码，查 `bind_codes` 未 consumed → 得 `user_id`；无匹配 → 审计「待认领」并返回 200（可人工补）。
  5. **计算周期**：按权威订单 `month` 判定 `month>=12 ? yearly : monthly`，`current_period_end = max(now, 现有到期日) + month 个月`（续订叠加）。可选 `AFDIAN_PLAN_ID` 白名单校验。
  6. **写库**：`upsert subscriptions`（status=active）、`update bind_codes set consumed=true`。
- **验签正确性保障**：`computeAfdianSign` 用 afdian 官方公开向量（`md5('123params{"a":333}ts1624339905user_idabc')==a4acc28b81598b7e5d84ebdc3e91710c`）做已知答案断言，避免自证。
- **失败可见性**：所有异常路径写入 `webhook_events` 审计表（raw payload + outcome），满足验收「不静默吞错」。

### 3.3 到期回落
- 无定时任务（MVP 不引 pfg_cron）。`useSubscription` 前端判定：`status==='active' && current_period_end > now()` 才算会员，否则 non-member。到期无需后台改状态即自然失效；`status` 字段仅作历史记录。

## 4. 前端

### 4.1 `useSubscription`（`src/lib/subscription/`，仿 holdings 的 provider/context/hook 三件套或轻量 hook）
- 返回 `{ state: 'loading'|'member'|'non-member', plan, periodEnd, refresh() }`。
- 读取逻辑：已登录 → `select * from subscriptions where user_id = auth.uid()` → 结合 `current_period_end` 判活。未登录/未配置 → non-member。
- 复用现有 `getSupabase()` / `useAuth()`。

### 4.2 `useWatchlist`
- `list()` / `add(item_type,item_key)`（走 `add_watchlist` RPC）/ `remove(id)`。
- add 返回订阅无效错误时，前端提示「需会员」。

### 4.3 页面/组件
- **升级页 `MembershipPage`**（新路由 `/membership`）：`AuthGate` 包裹；展示权益、定价卡（月/年）、绑定码块、爱发电按钮、当前订阅状态。
- **`MemberGate`** 组件：类比 `AuthGate`，非会员显示升级引导，会员渲染 children。
- **自选视图**：在雷达/主题页加「加自选」按钮（会员可点）；新增「我的自选」视图用 `MemberGate` 包裹，展示自选项当前状态（复用现有 themes/etfs 数据）。
- 导航加入口。

### 4.4 合规文案
- 升级页与自选视图页脚统一免责声明组件；文案审查禁止操作动词。

## 5. 配置与密钥
- 前端：无新增公开变量（爱发电链接可硬编码或走 `VITE_AFDIAN_MONTHLY_URL` / `VITE_AFDIAN_YEARLY_URL`）。
- Edge Function 环境：`AFDIAN_TOKEN`、`AFDIAN_USER_ID`、`SUPABASE_SERVICE_ROLE_KEY`、`SUPABASE_URL`（Supabase secrets，不进仓库）。
- 迁移手动在 SQL Editor 执行（沿用现有约定，README/注释标注）。

## 6. 兼容性 / 回滚
- 全为新增表/函数/路由/组件，不改动现有 pipeline 与既有页面数据流 → 零回归面。
- 回滚：撤下 `/membership` 路由与导航入口即对用户不可见；迁移可保留（无副作用）。Edge Function 可单独下线。

## 7. 测试策略
- 后端/迁移：SQL 无自动化测试框架，靠 Edge Function 单测（Deno test：验签、幂等、绑定码解析、周期计算，用 mock payload）。
- 前端：`useSubscription` 三态、到期回落；`useWatchlist` add/remove 与非会员报错路径；`MemberGate` 渲染分支。仿现有 `useEtfHoldings.test.ts` 用 vitest + supabase mock。
- 既有测试须保持全绿。

## 8. 已知风险 / 权衡
- **绑定码体验有摩擦**（用户需手动复制填留言）。可接受：MVP 验证付费意愿优先；二期迁官方支付时用回调直连消除。
- **未认领订单**（用户忘填/填错码）需人工兜底（看 `webhook_events`）。MVP 量小可控。
- **afdian 抽成与档位映射**：需在 afdian 后台建月/年两个方案，`plan_id` 映射写入 Edge Function 常量。
