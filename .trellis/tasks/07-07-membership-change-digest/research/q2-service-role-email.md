# Research: Q2 — service_role 能否读到用户邮箱

- **Query**: digest 发信需收件人邮箱；service_role key 能否读 `auth.users.email`？现有代码/迁移是否有 profiles 冗余 email？
- **Scope**: internal + 平台机制
- **Date**: 2026-07-07

## 结论（一句话）

**可读**。Supabase 的 `service_role` key 绕过 RLS，可直接查询 `auth.users`（含 `email` 列）。当前项目**无 profiles 冗余邮箱**，无需新增；直接用 service_role 查 `auth.users` 即可。

## 证据

### 1. 现有迁移中的用户模型

- 迁移文件：`backend/migrations/001_user_holdings.sql`、`002_user_events.sql`、`003_membership.sql`。
- 所有业务表均以 `user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE` 关联（见 001:16, 002:8, 003:16/47/68）。
- `grep -rniE "profiles|email" backend/migrations supabase` → **无 profiles 表、无冗余 email 列**。邮箱唯一来源是 Supabase 托管的 `auth.users.email`。

### 2. service_role 读 auth.users 的机制（平台约定）

- `service_role` key 具备 `bypassrls` 权限，绕过所有 RLS，可对 `auth` schema（含 `auth.users`）执行 SELECT。
- 这正是 design §5「收件人邮箱取自 Supabase `auth.users.email`（service_role 可读 auth.users）」的假设，成立。
- digest 脚本在 GitHub Actions 内用 `SUPABASE_SERVICE_ROLE_KEY` 连接，可 join / 批量查生效会员的邮箱。

## 实现提示（供阶段 4 复用）

- 用 service_role 查邮箱两种方式：
  1. PostgREST 无法直接暴露 `auth.users`（默认不在 API schema）；用 **Admin API**（`GET /auth/v1/admin/users` 或按 id 取）或直接 **Postgres 连接** 查 `auth.users`。
  2. 或建一个 `security definer` 视图/函数把需要的 `id,email` 暴露给 service_role（若走 PostgREST）。
- 由于本任务已在 Python + Actions 内跑，最简是**直连 Postgres**（`SUPABASE_DB_URL` / service connection）或调 Admin REST。二选一在阶段 4 定。

## 对 design / implement 的影响

- design §7 开放问题 2 可关闭：结论=可读，**不需要 profiles 冗余邮箱**。
- 阶段 4 需明确取邮箱的具体通道（Admin REST vs 直连 PG）——建议 Admin REST（只需 service_role key，无需额外 DB 连接串 secret）。这是实现细节，非阻塞。

## Caveats / Not Found

- 未实际用真实 key 联调验证（阶段 0 的 secret 尚未配置）——机制层面确定可读，联调留阶段 4。
- 若未来启用 Supabase 的 email 隐私/匿名策略，需复核；当前无此配置证据。
