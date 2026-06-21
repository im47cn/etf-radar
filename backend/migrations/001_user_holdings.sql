-- 001_user_holdings.sql
-- 用户持仓表 + RLS 策略
-- 在 Supabase SQL Editor 中执行（一次性）

-- ========== updated_at 通用触发器函数 ==========
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ========== user_holdings ==========
CREATE TABLE IF NOT EXISTS user_holdings (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  etf_code     text        NOT NULL,
  shares       numeric     NOT NULL CHECK (shares > 0),
  cost_price   numeric     CHECK (cost_price IS NULL OR cost_price > 0),
  note         text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, etf_code)
);

CREATE INDEX IF NOT EXISTS idx_holdings_user
  ON user_holdings (user_id);

DROP TRIGGER IF EXISTS trg_holdings_updated ON user_holdings;
CREATE TRIGGER trg_holdings_updated
  BEFORE UPDATE ON user_holdings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ========== RLS ==========
ALTER TABLE user_holdings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS holdings_own ON user_holdings;
CREATE POLICY holdings_own ON user_holdings
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== Realtime ==========
-- 在 Supabase 控制台 Database → Replication 中手动启用 user_holdings 的 Realtime publication
-- 或执行：
ALTER PUBLICATION supabase_realtime ADD TABLE user_holdings;
