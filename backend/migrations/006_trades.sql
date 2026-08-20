-- 006_trades.sql
-- SEPA 交易数据层：trades / trade_reviews / trading_settings 三表 + RLS
-- 在 Supabase SQL Editor 中执行（一次性）
--
-- 依赖 001_user_holdings.sql 已创建的通用触发器函数 set_updated_at()。
-- 若尚未执行 001，请先执行之，或取消下面这段兜底定义的注释：
-- CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
-- BEGIN NEW.updated_at = now(); RETURN NEW; END;
-- $$ LANGUAGE plpgsql;

-- ========== trades ==========
-- 交易事件流（append-only 语义，同日同标的多笔允许，无 UNIQUE）。
-- 当前持仓不做物化，由前端按 (trade_date, created_at) 升序事件流推导：
-- open 建仓 / add 加权平均 / reduce 扣减 / close 清仓。
CREATE TABLE IF NOT EXISTS trades (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  code        text        NOT NULL,                   -- A 股 6 位代码
  name        text        NOT NULL,
  side        text        NOT NULL CHECK (side IN ('open','add','reduce','close')),
  trade_date  date        NOT NULL,
  price       numeric     NOT NULL CHECK (price > 0),
  shares      int         NOT NULL CHECK (shares > 0),
  stop_after  numeric,                                -- 该笔之后的止损位；可空
  reason      text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trades_user
  ON trades (user_id);

DROP TRIGGER IF EXISTS trg_trades_updated ON trades;
CREATE TRIGGER trg_trades_updated
  BEFORE UPDATE ON trades
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE trades ENABLE ROW LEVEL SECURITY;

-- 本人读写（同 holdings_own 风格）。
DROP POLICY IF EXISTS trades_own ON trades;
CREATE POLICY trades_own ON trades
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== trade_reviews ==========
-- 复盘评分：写入只由 Actions (service_role key) 完成（绕过 RLS）；
-- 本人仅有 SELECT 策略。computed_at 为快照计算时间，无 updated_at 触发器。
CREATE TABLE IF NOT EXISTS trade_reviews (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  trade_id         uuid        NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
  review_date      date        NOT NULL,
  discipline_score int,                               -- 纪律分 0-100
  result_r         numeric,                           -- R 倍数（实现盈亏/初始风险额）
  mae_pct          numeric,                           -- 最大不利偏移 %
  events           jsonb,                             -- 当日信号事件快照
  computed_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_reviews_user
  ON trade_reviews (user_id);

CREATE INDEX IF NOT EXISTS idx_trade_reviews_trade
  ON trade_reviews (trade_id);

ALTER TABLE trade_reviews ENABLE ROW LEVEL SECURITY;

-- 故意不创建写策略 → authenticated 一律无法写；service_role 绕过 RLS 由 Actions 写入。
DROP POLICY IF EXISTS trade_reviews_own_select ON trade_reviews;
CREATE POLICY trade_reviews_own_select ON trade_reviews
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- ========== trading_settings ==========
-- 交易参数（本人单行）。默认值 = 规格 §1 第 7 条仓位计算器参数。
CREATE TABLE IF NOT EXISTS trading_settings (
  user_id                uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  equity_cny             numeric     CHECK (equity_cny IS NULL OR equity_cny > 0),
  risk_per_trade_pct     numeric     NOT NULL DEFAULT 0.75,
  max_positions          int         NOT NULL DEFAULT 5,
  max_position_pct       numeric     NOT NULL DEFAULT 20,
  max_portfolio_risk_pct numeric     NOT NULL DEFAULT 4,
  updated_at             timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_trading_settings_updated ON trading_settings;
CREATE TRIGGER trg_trading_settings_updated
  BEFORE UPDATE ON trading_settings
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE trading_settings ENABLE ROW LEVEL SECURITY;

-- 本人读写（同 trades_own 风格）。
DROP POLICY IF EXISTS trading_settings_own ON trading_settings;
CREATE POLICY trading_settings_own ON trading_settings
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== Realtime（可选） ==========
-- 若希望交易流水实时刷新（TradesProvider 已订阅 trades 表变更），执行：
-- ALTER PUBLICATION supabase_realtime ADD TABLE trades;
