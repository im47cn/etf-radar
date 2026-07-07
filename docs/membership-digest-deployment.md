# 会员每日变化摘要推送 — 联调 & 上线准备清单

> 二期功能，代码已在 `main`（commits c0e56a9 / 423ecc8 / ac13176）。契约见 `.trellis/spec/backend/membership-supabase.md`。
> 本清单是**你需要做的全部准备**，按顺序做完即可上线。

## 总览：4 个准备 + 3 步验证

```
准备① Resend 邮件服务   →  准备② Supabase 迁移+Function  →  准备③ GitHub secrets
                                        ↓
验证A 手动 dry-run 核对内容  →  验证B 单发真信  →  验证C 启用每日 cron
```

---

## 准备①：Resend 邮件服务（发信通道）
1. 注册 https://resend.com （免费额度足够 MVP）。
2. **Domains → Add Domain**，添加你的发件域名（如 `etf-radar.app` 或你拥有的域名）。
3. 按提示在域名 DNS 加 **SPF + DKIM** 记录，等待验证通过（绿勾）。
   - ⚠️ 没有自己的域名？Resend 有 `onboarding@resend.dev` 测试发件地址，但只能发给你自己注册邮箱，仅够验证、不能对用户发。正式上线需自有验证域名。
4. **API Keys → Create** → 复制 `re_xxx`（这是 `RESEND_API_KEY`）。
5. 记下发件地址（如 `digest@你的域名`）→ 这是 `NOTIFY_MAIL_FROM`。

## 准备②：Supabase（表 + 退订 Function）
1. **执行迁移**：SQL Editor 粘贴执行 `backend/migrations/004_notify.sql`（建 `notify_prefs` + `digest_log`）。
   - 依赖 001 的 `set_updated_at()`（已执行过）。
   - 验证：`select * from notify_prefs limit 1;` `select * from digest_log limit 1;` 不报错即建成。
2. **部署退订 Edge Function**（本机项目根目录）：
   ```bash
   supabase functions deploy notify-unsub --project-ref jamnwgemingjwudjhaak --no-verify-jwt
   ```
   - `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` 运行时自动注入，无需设。
   - 验证：`curl "https://jamnwgemingjwudjhaak.supabase.co/functions/v1/notify-unsub"` → 应返回「缺少参数」HTML（说明函数活着）。

## 准备③：GitHub Actions secrets / variables
在 **GitHub → Settings → Secrets and variables → Actions**：
- **Secrets**（加密）：
  - `RESEND_API_KEY` = 准备①的 `re_xxx`
  - `SUPABASE_URL`（若还没有）= `https://jamnwgemingjwudjhaak.supabase.co`
  - `SUPABASE_SERVICE_ROLE_KEY` = Supabase → Settings → API 的 service_role key
- **Variables**（明文，非密钥）：
  - `NOTIFY_MAIL_FROM` = 准备①的发件地址（如 `digest@你的域名`）

---

## 验证A：手动 dry-run（不真发，只看内容）
1. GitHub → **Actions → Membership Change Digest → Run workflow**。
2. `dry_run` 保持 **true**（默认）。可选 `run_date` 指定某个有数据的交易日。
3. 跑完看 job 日志：会打印「将发给 <user> <email>：<邮件正文>」+ 写 `digest_log(note='dry-run')`。
4. **核对**：文案是否客观（无买入/加仓等）、C 是否置顶、变化描述是否合理。
   - 没内容？说明当天你的自选无 A/C/D 变化，或你还不是会员/无自选——先确保有一个会员账号加了自选。

## 验证B：单发一封真信
1. 确认你自己是**生效会员**且加了自选（`/membership` + `/watchlist`）。
2. Run workflow，`dry_run` 设 **false**。
3. 检查你的邮箱是否收到摘要邮件，**点一次退订链接** → 应打开「已退订」页；再查 `notify_prefs.email_enabled` 应为 false。
4. （测完把自己的 `email_enabled` 改回 true 继续接收。）

## 验证C：启用每日自动
1. 编辑 `.github/workflows/membership-digest.yml`，取消 `schedule` 两行注释（BJT 18:30）。
2. 提交 → 之后每个交易日 EOD 归档后自动跑真发。

---

## 依赖关系速查
| 你要做 | 阻塞什么 |
|---|---|
| Resend 域名验证 + key | 真发信（验证B/C）；dry-run 不需要 key |
| 迁移 004 | dry-run 也需要（要写 digest_log）——**这个必须先做** |
| notify-unsub 部署 | 邮件里的退订链接可点 |
| Actions secrets | workflow 能查 Supabase / 发信 |

## 排障
- **dry-run 报 "缺少环境变量"**：Actions secrets 没配全（至少 `SUPABASE_URL`+`SUPABASE_SERVICE_ROLE_KEY`）。
- **真发报 "非 dry-run 但缺 RESEND_API_KEY"**：`RESEND_API_KEY` secret 没配。
- **发信 Resend 4xx**：发件域名未验证，或 `NOTIFY_MAIL_FROM` 与验证域名不符。
- **没人收到 / 全 skipped_no_change**：当天无会员自选发生 A/C/D 变化，属正常（保持信号高）。
- **查发送结果**：Supabase `digest_log` 表，`outcome ∈ {sent, skipped_no_change, skipped_unsub, skipped_idempotent, failed}`。

## 战略提醒
MVP 仍 **0 真实订单**——这套推送上线后，**优先监控退订率/打开率而非发送量**。若退订率高，问题多半在触发集选择（A/D 噪音，signal 偏弱），届时可收紧跨档门槛（仍复用现有分档，不引新魔数）。
