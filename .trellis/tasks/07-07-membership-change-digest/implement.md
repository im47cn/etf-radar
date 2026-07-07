# 执行计划 — 会员每日变化摘要邮件推送

按依赖顺序分 6 阶段，每阶段末含验证/评审点。子代理不做 git commit。

## 阶段 0：外部准备（人工，可并行）
- [ ] 注册 Resend，验证发件域名（SPF/DKIM），取 `RESEND_API_KEY`。
- [ ] GitHub 仓库配置 secrets：`RESEND_API_KEY`、`SUPABASE_SERVICE_ROLE_KEY`（若未有）、确认 `SUPABASE_URL`。
- **Gate**：拿到 Resend key + 域名验证通过，方可联调阶段 4/5。

## 阶段 1：研究确认 ✅ 已完成（research/ 下 q1-q4）
- [x] **B 数据依赖不成立 → 剔除 B**，触发集 = A+C+D（research/q1）。
- [x] service_role 可读 `auth.users.email`，无需 profiles（research/q2）。
- [x] 温度 4 档边界 30/50/70，真源 `frontend/src/lib/breadthColor.ts` `breadthTier()` L58-64（research/q3）；Python 同值移植 + 单测钉边界。
- [x] snapshot：themes/etfs 每日齐全；`market_temperature` 27/30 天缺 → C 对缺失降级；prev-day 按实际目录回溯（research/q4）。
- prd/design 已据此回改（B 剔除、开放问题关闭）。

## 阶段 2：数据层（迁移 + RLS）
- [ ] `backend/migrations/004_notify.sql`：`notify_prefs`、`digest_log` 两表 + 索引 + RLS + `set_updated_at`。
- [ ] 幂等约束 `digest_log UNIQUE(run_date,user_id)`；`notify_prefs.unsub_token UNIQUE`。
- **验证**：SQL Editor 执行无错；RLS 手测（本人可读 notify_prefs、digest_log 对 authenticated 不可见）。

## 阶段 3：变化计算核心（纯逻辑，最先可测）
- [ ] `backend/src/notify/changes.py`：读今日/上一交易日 snapshot → 计算 **A/C/D（B 已剔除）** → 按标的聚合降噪（A/D 同标的合一行，优先级 A>D）→ 结构化变化列表。纯函数、无 IO。
- [ ] prev-day 解析：按 `data/snapshots/` 实际存在目录回溯取上一交易日（非目录名减一天）；温度按序列内 `date` 对齐。
- [ ] C 分档：Python 侧同值移植 30/50/70（对齐 `breadthColor.ts`），`market_temperature` 缺失日跳过 C 不报错。
- [ ] 单测覆盖：象限迁移/未迁移、composite 跨 50/未跨、温度档切换/未切、**温度数据缺失跳过 C**、同标的 A+D 合并、prev-day 缺失降级、空自选、**温度边界值 30/50/70 钉死**。
- **验证**：`cd backend && uv run --all-extras pytest tests/test_notify_changes.py -v`。

## 阶段 4：编排 + Supabase 查询 + 发信（IO 层）
- [ ] `backend/src/notify/digest.py`：查生效会员+watchlist+notify_prefs(service_role) → 逐会员套用阶段 3 变化 → 有变化拼邮件 → Resend 发信 → 写 digest_log。
- [ ] 邮件模板（纯文本+极简 HTML），页脚免责声明 + 退订链接；合规文案零操作动词。
- [ ] 单测：会员过滤、退订跳过、无变化跳过、发信失败隔离（mock Supabase + Resend）。
- **验证**：pytest 全绿；本地用 dry-run 模式（不真发）打印将发内容核对。

## 阶段 5：退订 Edge Function
- [ ] `supabase/functions/notify-unsub/`：GET `?token=` → 匹配 notify_prefs 置 email_enabled=false → HTML「已退订」。无效 token 友好提示。
- [ ] Deno 单测：有效/无效 token。
- **验证**：`deno test`；部署后 curl 验证。

## 阶段 6：触发编排 + 整合验收
- [x] 独立 workflow `.github/workflows/membership-digest.yml`（手动触发版）：`workflow_dispatch`（dry_run 输入默认 true、可选 run_date）+ 交易日门 + uv sync + `python -m src.notify.digest`。cron 注释待联调后启用（BJT 18:30，EOD 归档后）。NOTIFY_DRY_RUN 仅 dispatch+dry_run=true 时空跑，schedule 真发。
- [ ] 联调（需 Resend 域名 + 迁移 004 + secrets）后：先手动 dry-run 核对 → 关闭 dry_run 真发 → 启用 cron。
- [ ] 逐条核对 prd Acceptance Criteria；合规文案终审。
- [ ] `trellis-check` → `trellis-update-spec` → 提交 → `/trellis:finish-work`。

## 验证命令速查
- 变化计算：`cd backend && uv run --all-extras pytest tests/test_notify_changes.py -v 2>&1 | tail -20`
- notify 全量：`cd backend && uv run --all-extras pytest tests/ -k notify 2>&1 | tail -15`
- 退订 Function：`cd supabase/functions/notify-unsub && deno test 2>&1 | tail -20`

## 回滚点
- 移除 digest job → 立即停发（阶段 6）。
- 迁移 004、notify 模块、退订 Function 均纯新增，可保留无副作用。
- 阶段 1 若判 B 数据不可得 → 缩范围为 A/C/D，不阻塞其余。
