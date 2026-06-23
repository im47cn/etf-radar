-- 002_user_events.sql
-- 用户事件表 + RLS 策略
-- 在 Supabase SQL Editor 中执行（一次性）

-- ========== user_events ==========
CREATE TABLE IF NOT EXISTS user_events (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  event_type      text        NOT NULL,
  -- 'theme_quadrant_change' | 'theme_strength_cross_up' | 'theme_strength_cross_down' | 'theme_signal_change'
  theme_id        text        NOT NULL,
  event_signature text        NOT NULL,
  -- 例: 'theme_quadrant_change:cn_tech:2026-06-23:leading_to_weakening'
  payload         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  asof_date       date        NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  read_at         timestamptz,
  UNIQUE (user_id, event_signature)
);

CREATE INDEX IF NOT EXISTS idx_events_user_time
  ON user_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_unread
  ON user_events (user_id)
  WHERE read_at IS NULL;

-- ========== RLS ==========
ALTER TABLE user_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS events_own ON user_events;
CREATE POLICY events_own ON user_events
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== Realtime ==========
ALTER PUBLICATION supabase_realtime ADD TABLE user_events;
