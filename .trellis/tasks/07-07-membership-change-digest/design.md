# 技术设计 — 会员每日变化摘要邮件推送

## 1. 架构总览

```
GitHub Actions: cn-eod-archive (18:00 BJT 收盘归档后)
        │ 新增 step / 新 workflow「digest」
        ▼
Python 脚本 backend/src/notify/digest.py
  1. 读今日 vs 昨日 snapshot (data/snapshots/<today>, <prev>)
  2. 计算全局 + 每标的的状态变化 (A/B/C/D)
  3. 查 Supabase: 生效会员 + 各自 watchlist + notify_prefs(未退订)
  4. 逐会员按自选聚合变化 → 有变化才拼邮件
  5. Resend 发信 + 记录发送结果
        │ service_role 读 Supabase        │ HTTPS 发信
        ▼                                  ▼
   Supabase Postgres                    Resend API
   (subscriptions/watchlist/notify_prefs/digest_log)
```

**为何放 GitHub Actions Python 而非 Supabase Edge Function**：变化=今日 vs 昨日 snapshot 的时间差，snapshot 本地就有且已有 Python 解析代码；Edge Function 侧要额外存/取昨日状态，反而绕。会员/自选数据用 service_role 一次性查出。

## 2. 数据来源与变化判定

### 2.1 输入 snapshot 字段（已核实）
- `themes.json` → `themes[]`：`id, name, strength{short,mid,long,composite}, rank`。
- `etfs.json` → `etfs[]`：`code, name, theme_id, strength`。
- `market_temperature.json` → `periods{ma20,ma60,ma120}`（全市场/行业宽度时间序列）。

### 2.2 触发规则（阈值复用现有分档边界，无新魔数）
- **A 象限迁移**（per 自选 theme）：象限 = (`strength.long` vs 50, `strength.short` vs 50) 四象限。今日象限 ≠ 上一交易日 → 触发。
- **D 强度上穿/下穿 50**（per 自选 theme/etf）：`strength.composite` 上一交易日/今日跨越 50 → 触发。
- **C 全市场温度档位切换**（全局）：4 档边界 **30/50/70**（真源 `frontend/src/lib/breadthColor.ts` 的 `breadthTier()` L58-64：`[0,30)冰点/[30,50)偏冷/[50,70)偏暖/[70,100]过热`）。**跨语言无法 import——Python 侧同值移植 + 单测钉死边界**。取全市场序列（按序列内 `date` 对齐，latest 可能落后目录约 1 交易日）；档位变化 → 触发置顶。**`market_temperature` 缺失日（历史 27/30 缺）→ 跳过 C 不报错**。
- ~~**B 宽度跨档**~~：**research 剔除**（theme/ETF 无宽度维度、无 theme→行业映射，见 research/q1）。

### 2.3 聚合降噪（关键）
- **按标的聚合，不按触发器**。同一自选项当天同时触发 A/D → 合并一行，取最显著变化（优先级 A > D）+ 强度数值。
- C 单独置顶，全员共享。
- 每标的一行文案示例：`• [半导体] 转强：进入强势象限，强度 48→61`。

## 3. 数据模型（新增迁移 `backend/migrations/004_notify.sql`）
沿用现有约定（`auth.users` 外键、`set_updated_at`、RLS `auth.uid()`）。

### 3.1 `notify_prefs`
```
user_id      uuid PK REFERENCES auth.users(id) ON DELETE CASCADE
email_enabled boolean NOT NULL DEFAULT true   -- 退订即置 false
unsub_token  text UNIQUE                       -- 一键退订用的随机 token
created_at/updated_at timestamptz
```
- RLS：本人 SELECT/UPDATE（供前端会员中心开关）。退订链接走 Edge Function 用 token 匹配（无需登录）。

### 3.2 `digest_log`（审计/幂等）
```
id uuid PK; run_date date; user_id uuid; outcome text  -- sent/skipped_no_change/skipped_unsub/failed
note text; created_at timestamptz
UNIQUE(run_date, user_id)   -- 幂等：同一天同一用户只发一次
```
- RLS：仅 service_role（无 authenticated 策略）。

## 4. 退订（一键，无需登录）
- 邮件含链接 `https://<ref>.supabase.co/functions/v1/notify-unsub?token=<unsub_token>`。
- 复用/新增一个轻量 Edge Function：按 token 匹配 `notify_prefs` → 置 `email_enabled=false` → 返回人可读 HTML「已退订」。
- token 随机不可枚举；退订是幂等写。

## 5. 发信
- **Resend**（`RESEND_API_KEY`，Actions secret）。收件人邮箱取自 Supabase `auth.users.email`（service_role 可读 `auth.users`）。
- 发件域名需在 Resend 验证（SPF/DKIM）。发信失败记 `digest_log(outcome='failed')`，不中断其他用户。
- 邮件模板：纯文本 + 极简 HTML；页脚含免责声明 + 退订链接。**全文零操作动词**。

## 6. 触发编排
- 在 `cn-eod-archive.yml` 归档成功后追加一个 `digest` job（或独立 workflow `depends on`），仅工作日 EOD 跑一次。
- 幂等：`digest_log UNIQUE(run_date,user_id)`；重跑当日不重复发。
- 配置：`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`RESEND_API_KEY` 作 Actions secrets。

## 7. 开放问题 / 风险
1. ~~B 触发数据依赖~~ **已关闭（research/q1）：剔除 B**，触发集 = A+C+D。
2. ~~auth.users.email 可读性~~ **已关闭（research/q2）：service_role 可读 `auth.users.email`，无需 profiles 冗余**。取邮箱通道（Admin REST vs 直连 PG）留阶段 4 定。
3. **prev-day snapshot 解析**：无现成"上一交易日"工具函数 → 按 `data/snapshots/` 实际存在目录回溯（非目录名减一天）。`market_temperature` 序列按内部 `date` 对齐，latest 可能落后目录约 1 交易日。
4. **阈值噪音**：跨档过频则邮件疲劳。上线后观察，必要时提门槛（仍复用现有分档，不引魔数）。
5. **合规复核**：邮件模板文案过一遍「零操作动词」终审。

## 8. 兼容性 / 回滚
- 全为新增：迁移 004、`backend/src/notify/`、一个 digest job、一个退订 Edge Function。不改现有管线与页面。
- 回滚：移除 digest job 即停发；迁移与 Edge Function 可保留（无副作用）。

## 9. 测试策略
- Python 单测（pytest，复用现有 backend 测试体系）：变化 diff（A/C/D 各含跨档/未跨档用例）、按标的聚合降噪、会员过滤、退订跳过、昨日 snapshot 缺失降级、邮件文案无操作动词断言。
- 退订 Edge Function：Deno 单测（有效/无效 token）。
- 既有前后端测试全绿。
