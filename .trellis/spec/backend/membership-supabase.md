# 会员订阅 / Supabase 服务端层 code-spec

> **背景例外**：本项目后端主体是「无 DB / 无 web 服务」的数据管线。**会员订阅是唯一例外**——它引入 Supabase（Postgres + RLS + Edge Function）作为服务端。此 spec 只约束会员子系统，不影响数据管线铁律。

## Scenario: 爱发电订阅 → Supabase 会员激活

### 1. Scope / Trigger
- 触发：DB schema 迁移 + Edge Function（webhook）+ env 密钥 + 跨层门控契约。
- 首次实现：commit `ea82c66`（数据层/前端/UI）、`218e43e`（Edge Function）。

### 2. Signatures
- **迁移**：`backend/migrations/003_membership.sql`（Supabase SQL Editor 手动执行，依赖 001 的 `set_updated_at()`）。
- **表**：`subscriptions`(user_id UNIQUE, plan, status, current_period_end, source, afdian_trade_no)、`bind_codes`(user_id, code UNIQUE, consumed)、`watchlist`(user_id, item_type, item_key, UNIQUE 三元组)、`webhook_events`(source, out_trade_no, outcome, raw_payload jsonb, note)。
- **RPC（SECURITY DEFINER）**：
  - `issue_bind_code() -> text`（复用本人未 consumed 有效码，否则生成 8 位 base32）
  - `add_watchlist(p_item_type text, p_item_key text) -> watchlist`（内部校验订阅有效性，非会员 `RAISE EXCEPTION 'NOT_A_MEMBER'`）
- **Edge Function**：`supabase/functions/afdian-webhook`，POST，`--no-verify-jwt`，恒返回 `{ec:200}`。
- **前端 hook**：`useSubscription() -> {state:'loading'|'member'|'non-member', plan, periodEnd, refresh}`；`useWatchlist() -> {items, add, remove}`。

### 3. Contracts
- **afdian query-order 请求**（验真用）：`POST https://afdian.com/api/open/query-order`（**必须用 `.com`**——`.net` 已停用，Supabase 边缘 DNS 解析 `.net` 直接失败），body `{user_id, params:'{"out_trade_no":"…"}', ts, sign}`，`sign = md5(token + "params"+params + "ts"+ts + "user_id"+user_id)`（key 升序拼接、**小写 md5**、无分隔符）。
- **env（Edge Function secrets）**：`AFDIAN_TOKEN`、`AFDIAN_USER_ID` 必填；`AFDIAN_PLAN_ID` 可选白名单。`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` **由 Supabase 运行时自动注入，禁止手动 `secrets set`**（`SUPABASE_` 前缀被保留、会被拒）。
- **前端 env**：`VITE_AFDIAN_MONTHLY_URL`、`VITE_AFDIAN_YEARLY_URL`（缺省 `#`）。
- **周期**：权威订单 `month>=12 → 'yearly'` 否则 `'monthly'`；`current_period_end = max(now, 现有到期日) + month 个月`（续订叠加）。

### 4. Validation & Error Matrix（webhook outcome）
| 条件 | outcome | 是否激活 |
|---|---|---|
| ping/test 回调 | （直接 `{ec:200}`） | 否 |
| 幂等：afdian_trade_no 已存在 | `dup` | 否（已激活过） |
| query-order 核实失败 / 订单不存在 / `status≠2` | `order_verify_failed` | 否 |
| remark 无绑定码 | `no_bind_code` | 否（待人工认领） |
| 绑定码查无匹配 / 已 consumed | `no_user` | 否 |
| plan_id 白名单不匹配 | `plan_mismatch` | 否 |
| 全部通过 | `activated` | 是 |

所有失败路径**必落 `webhook_events` 审计 + 恒返回 `{ec:200}`**（afdian 非 200 会重试）。

### 5. Good/Base/Bad Cases
- Good：会员正确填绑定码 → query-order status=2 → 激活，到期日正确。
- Base：续订 → 在原到期日上叠加 month 个月。
- Bad：伪造 webhook（不调 query-order 就信 payload）→ 被伪造金额/月数欺骗。**必须以 query-order 返回订单为权威源**。

### 6. Tests Required
- Edge Function（`deno test`，16 passed）：md5 官方向量断言、ping、核实通过/失败、status≠2、幂等 dup、绑定码缺失/无效、月/年周期、续订叠加、plan 白名单。
- 前端（vitest）：`useSubscription` 三态 + 到期回落；`useWatchlist` add/remove + 非会员 add 报错。
- 断言点：sign 已知答案 `md5('123params{"a":333}ts1624339905user_idabc')==a4acc28b81598b7e5d84ebdc3e91710c`。

### 7. Wrong vs Correct

#### Wrong（首版踩过的坑）
```ts
// ❌ 对 webhook payload 的 sign 字段验签
if (md5(token + stableStringify(payload.data)) !== payload.sign) reject()
// afdian webhook 回调根本没有 sign 字段 —— 验的是不存在的东西, 且信任了可伪造的 payload
```

#### Correct
```ts
// ✅ 拿 out_trade_no 反向调 query-order API 核实, 以返回订单为权威源
const order = await verifier.fetchOrder(payload.data.order.out_trade_no)
if (!order || order.status !== 2) return audit('order_verify_failed')
// 之后 month/plan_id/remark 全部取自 order, 不取 webhook payload
```

---

## 门控铁律（跨层）
1. **会员状态不可前端伪造**：`subscriptions` 无 authenticated 写策略，只有 Edge Function 用 service_role 写。
2. **「仅会员可写」是服务端硬约束**：走 `add_watchlist` RPC 内校验，不靠前端 `useSubscription`（后者仅 UX）。
3. **`webhook_events` 对 authenticated 完全不可见**（启用 RLS 但不建任何策略）；将来做运营后台勿用 authenticated 直连。
4. **到期回落零后台**：`useSubscription` 前端判 `status==='active' && periodEnd>now()`，无定时任务。

## 部署 Runbook（要点）
- `supabase functions deploy afdian-webhook --project-ref <REF> --no-verify-jwt`（无需 link，直接带 `--project-ref`；deploy 命令须在**项目根目录**跑，否则找不到 `supabase/functions/...`）。
- `supabase secrets set AFDIAN_TOKEN=… AFDIAN_USER_ID=…`（`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` 运行时自动注入，禁手动设）。
- SQL Editor 执行 `003_membership.sql`。
- afdian 后台回调 URL：`https://<REF>.supabase.co/functions/v1/afdian-webhook`。
- 上线前用一笔真实小额订单端到端联调（验真已用官方向量证明，剩字段名以真实响应为准）。

## 上线排障踩坑（2026-07-04 实战）
1. **afdian ping 报「请检查地址」**：多为 ping 响应体没有 `{"ec":200}`。① 确认部署的是本函数（curl 应返回带 `ec` 的体，而非占位 `{"ok":true}`）② ping(`data.type==='test'`) 必须在 `loadEnv()` 之前放行——否则 secrets 未设全时 loadEnv 抛异常→500→ping 失败。
2. **`dns error: failed to lookup afdian.net`**：域名用错。**必须 `afdian.com`**，`.net` 已停用、Supabase 边缘解析失败。
3. **`order_verify_failed / query-order 未核实到订单`** 有歧义，可能是：① 订单真不存在（如 afdian 后台「测试推送」用的是官方文档**示例假单号** `202106232138371083454010626`，查无属正常）② **sign/token 错误**（`ec=400005 sign validation failed`）。代码已对 ec≠200 单独打日志区分。**token 轮换后必须同步更新 Supabase secret**，否则一直 sign 失败。
4. **快速验证 token/签名**：本机 `deno run` 直调 query-order（params `{"page":1}` 列订单），`ec=200 em=order` 即 token+签名有效；`ec=400005` 即 token 错。
5. **access token 反复贴/撤易 401**：优先 `supabase login`（磁盘持久化），避免用一次撤一次导致 deploy 中途 401。
