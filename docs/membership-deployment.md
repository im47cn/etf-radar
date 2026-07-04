# 会员订阅 MVP — 部署 Runbook

> 面向运维/开发者的上线操作手册。代码已在 `main`（commits `ea82c66` / `218e43e`）。
> 契约与设计见 `.trellis/spec/backend/membership-supabase.md`。

## 架构一图

```
爱发电 afdian ──webhook POST──► Supabase Edge Function「afdian-webhook」
  用户订阅付款                       │ 拿 out_trade_no 反向调 query-order 核实
                                     ▼
                            Supabase Postgres (RLS)
                            subscriptions / bind_codes / watchlist / webhook_events
                                     ▲
前端 GitHub Pages ──useSubscription/useWatchlist──┘
```

- 收款：爱发电（个人可用、免营业执照/免 ICP 备案）。
- 服务端：Supabase（Postgres + RLS + 一个 Edge Function）。**无自有后端服务器。**
- 账号打通：绑定码（用户在 afdian 订单留言填码 → webhook 匹配 Supabase user）。

---

## 前置条件

- [ ] 已有 Supabase 项目（现有 OAuth 登录复用它）。
- [ ] 已有爱发电账号，建好订阅方案（至少「月度 ¥6」；年度 ¥58 需**单独建方案**才能给折扣）。
- [ ] 本机已装 Supabase CLI：`brew install supabase/tap/supabase`（已装 2.109.0）。
- [ ] 已装 deno（跑 Edge Function 单测用，可选）。

### 手头需要的凭证
| 变量 | 从哪拿 |
|---|---|
| `AFDIAN_USER_ID` | 爱发电开发者后台 |
| `AFDIAN_TOKEN` | 爱发电开发者后台（⚠️ 用**新轮换**的，旧的已在聊天记录泄漏） |
| `AFDIAN_PLAN_ID`（可选） | 爱发电方案页；留空则接受该创作者全部订阅订单 |
| `PROJECT_REF` | Supabase Dashboard → Project Settings → General → Reference ID |

> `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` **由 Edge Function 运行时自动注入，不要手动设**（`SUPABASE_` 前缀被保留，`secrets set` 会拒绝）。

---

## 步骤

### 1. 建表（Supabase SQL Editor）
把 `backend/migrations/003_membership.sql` 全文粘进 **Supabase Dashboard → SQL Editor** 执行一次。
- 依赖 `001_user_holdings.sql` 里的 `set_updated_at()`（若没执行过 001 需先执行）。
- 建成 4 表 + RLS + 2 个 RPC（`issue_bind_code` / `add_watchlist`）。

**验证**（SQL Editor 里）：
```sql
-- 应报错 NOT_A_MEMBER（当前账号非会员）
select add_watchlist('theme', 'test');
-- 应返回一个 8 位码
select issue_bind_code();
```

### 2. 部署 Edge Function（本机终端，项目根目录）
```bash
supabase login
supabase link --project-ref <PROJECT_REF>
supabase secrets set AFDIAN_TOKEN=<新token> AFDIAN_USER_ID=<user_id>
# 可选白名单：supabase secrets set AFDIAN_PLAN_ID=<plan_id>
# 可选支付失败告警：supabase secrets set SERVERCHAN_SENDKEY=<Server酱SENDKEY>
supabase functions deploy afdian-webhook --no-verify-jwt
```
- **支付失败告警**：配置 `SERVERCHAN_SENDKEY`（https://sct.ftqq.com/ 获取）后，真实付款单未激活（no_bind_code/no_user/plan_mismatch/order_verify_failed/error）会推送微信告警（自动过滤 afdian 测试推送假单）；不配置则不告警。告警含订单金额/留言/afdian 用户/处理建议，及两个快捷操作：**🔄 一键重试**（修好根因后点此重跑该订单，HMAC 签名、仍走完整核实）、**📋 Supabase 表编辑器**跳转。
- `--no-verify-jwt` 必须：afdian 匿名 POST，无 JWT。
- 部署输出函数地址：`https://<PROJECT_REF>.supabase.co/functions/v1/afdian-webhook`

### 3. 配置 afdian webhook
爱发电开发者后台 → webhook 回调 URL 填上一步的函数地址。
- afdian 会先发 `data.type='test'` 的 ping，函数已返回 `{ec:200}` 通过。

### 4. 前端配置 + 重部署
在前端构建环境配：
```
VITE_AFDIAN_MONTHLY_URL=https://www.afdian.com/a/im47cn
VITE_AFDIAN_YEARLY_URL=<年费方案链接，建好后填>
```
重新 build 并部署到 GitHub Pages。

### 5. 端到端联调（上线前必做）
用一个真实账号走完整链路：
1. 登录站点 → `/membership` 升级页 → 复制绑定码。
2. 去爱发电订阅 ¥6 月度，**在订单留言粘贴绑定码**。
3. 等 webhook 触发（几秒）。
4. 回站点刷新 → 应显示「会员生效中 + 到期日」，`/watchlist` 可加自选。

**排查**（若没激活）：Supabase → Table Editor 看 `webhook_events` 的 `outcome`：
| outcome | 含义 | 处理 |
|---|---|---|
| `order_verify_failed` | query-order 核实失败 | 查 token/user_id 是否正确、sign 是否小写 |
| `no_bind_code` | 留言没识别到码 | 提醒用户留言填码 |
| `no_user` | 码查无匹配/已用 | 让用户在升级页重取码 |
| `plan_mismatch` | plan_id 白名单不符 | 核对 `AFDIAN_PLAN_ID` |
| `dup` | 重复回调 | 正常（幂等） |
| `activated` | 成功 | ✅ |

### 上线实战踩坑（2026-07-04）
- **afdian ping 报「请检查地址」**：先 `curl -X POST <URL> -d '{"data":{"type":"test"}}'`，应返回带 `ec` 的体（如 `{"ec":200,...}`）。若返回 `{"ok":true}` 说明部署的不是本函数，需 `deploy` 覆盖。
- **`order_verify_failed` 但订单确实存在**：多半是 **Supabase secret 里的 `AFDIAN_TOKEN` 是旧的/已轮换**——token 换了必须同步更新 secret，否则 `ec=400005 sign validation failed`。快速自查：本机 `deno run` 直调 query-order（`params={"page":1}`），`ec=200 em=order` 即 token 有效。
- **afdian 后台「测试推送」永远 `order_verify_failed`**：它用官方文档示例假单号 `202106232138371083454010626`，query-order 查无属正常。**只有真实付款订单能激活**。
- **query-order DNS 失败**：域名必须 `afdian.com`（`.net` 已停用）。
- **deploy 报 401 / 找不到文件**：deploy 要在**项目根目录**跑；access token 反复贴撤易 401，优先 `supabase login`。

---

## 安全清单
- [ ] **轮换泄漏的 afdian token**（旧 token 已在对话明文出现）。
- [ ] `service_role key` 只在 Edge Function（自动注入），绝不进前端/仓库。
- [ ] `webhook_events` 仅 service_role 可见；做运营后台勿用 authenticated 直连。
- [ ] 会员相关 UI 文案审查：无操作动词（买入/加仓/卖出），免责声明到位。

## 回滚
- 撤下前端 `/membership` `/watchlist` 路由入口 → 对用户不可见。
- `supabase functions delete afdian-webhook` → 停收款回调。
- 迁移为纯新增表，无副作用，可保留。

## 二期 Backlog（不在本次）
- 邮件「每日变化摘要」推送（Resend + pg_cron）——留存引擎。
- 全量历史快照回看 + CSV 导出（需 pipeline 公私数据拆分）。
- 微信/支付宝官方支付迁移（降抽成 + 去绑定码摩擦）。
- afdian 年费独立方案。
