-- 005_holdings_free_limit.sql
-- 免费用户最多 5 支持仓；会员不限。服务端硬约束，防前端直连绕过。
-- 在 Supabase SQL Editor 中执行（一次性）。依赖 001_user_holdings / 003_membership。
--
-- 设计要点：
--   * 仅拦 BEFORE INSERT —— 给已有 ETF 加仓走 upsert 的 ON CONFLICT→UPDATE 路径，
--     编辑、删除均不触发本触发器，故不受限制。
--   * 存量用户已录入的持仓一律保留、不删不改；超过 5 支的老用户保留全部，
--     仅"新增第 6 支不同 ETF"被拦，升级会员即解锁。

CREATE OR REPLACE FUNCTION enforce_free_holdings_limit()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER               -- 需读 subscriptions（RLS 仅本人可读），提权保证稳健
SET search_path = public
AS $$
DECLARE
  is_member boolean;
  cnt       int;
BEGIN
  -- 会员校验：status=active 且 current_period_end 在未来（与 add_watchlist 同口径）
  SELECT EXISTS (
    SELECT 1 FROM subscriptions
    WHERE user_id = NEW.user_id
      AND status = 'active'
      AND current_period_end IS NOT NULL
      AND current_period_end > now()
  ) INTO is_member;

  IF is_member THEN
    RETURN NEW;                -- 会员不限
  END IF;

  SELECT count(*) INTO cnt FROM user_holdings WHERE user_id = NEW.user_id;
  IF cnt >= 5 THEN
    RAISE EXCEPTION 'HOLDINGS_LIMIT'
      USING HINT = '免费版最多 5 支持仓，升级会员解锁不限';
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_holdings_free_limit ON user_holdings;
CREATE TRIGGER trg_holdings_free_limit
  BEFORE INSERT ON user_holdings
  FOR EACH ROW EXECUTE FUNCTION enforce_free_holdings_limit();
