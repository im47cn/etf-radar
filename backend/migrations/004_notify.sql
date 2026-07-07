-- 004_notify.sql
-- 会员每日变化摘要邮件推送（二期）：notify_prefs / digest_log 两表 + 索引 + RLS + set_updated_at 触发器
-- 在 Supabase SQL Editor 中执行（一次性）。
--
-- 依赖 001_user_holdings.sql 已创建的通用触发器函数 set_updated_at()。
-- 若尚未执行 001，请先执行之，或取消下面这段兜底定义的注释：
-- CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
-- BEGIN NEW.updated_at = now(); RETURN NEW; END;
-- $$ LANGUAGE plpgsql;

-- ========== notify_prefs ==========
-- 用户的推送偏好。退订即置 email_enabled=false。
-- unsub_token 供一键退订 Edge Function（无需登录）按 token 匹配置退订。
CREATE TABLE IF NOT EXISTS notify_prefs (
  user_id       uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email_enabled boolean     NOT NULL DEFAULT true,
  unsub_token   text        UNIQUE,                 -- 随机不可枚举 token，退订用
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_notify_prefs_updated ON notify_prefs;
CREATE TRIGGER trg_notify_prefs_updated
  BEFORE UPDATE ON notify_prefs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE notify_prefs ENABLE ROW LEVEL SECURITY;

-- 本人可读（会员中心展示开关状态）。
DROP POLICY IF EXISTS notify_prefs_own_select ON notify_prefs;
CREATE POLICY notify_prefs_own_select ON notify_prefs
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- 本人可改（会员中心手动开关）。退订链接走 Edge Function 以 service_role 按 token 改，不依赖此策略。
DROP POLICY IF EXISTS notify_prefs_own_update ON notify_prefs;
CREATE POLICY notify_prefs_own_update ON notify_prefs
  FOR UPDATE TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== digest_log ==========
-- 每日摘要发送审计 + 幂等。每个用户每个 run_date 只落一条，重跑当日不重复发。
-- 无 authenticated 策略 → 仅 service_role 可读写（同 webhook_events 风格）。
CREATE TABLE IF NOT EXISTS digest_log (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_date    date        NOT NULL,
  user_id     uuid        NOT NULL,                 -- 不设外键：审计记录应在用户删除后仍可留存
  outcome     text        NOT NULL,                 -- sent / skipped_no_change / skipped_unsub / failed
  note        text,                                 -- 处理结论/异常信息
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_date, user_id)                        -- 幂等：同一天同一用户只发一次
);

CREATE INDEX IF NOT EXISTS idx_digest_log_run_date
  ON digest_log (run_date);

ALTER TABLE digest_log ENABLE ROW LEVEL SECURITY;
-- 故意不创建任何策略 → authenticated 一律无权限；service_role 绕过 RLS。
