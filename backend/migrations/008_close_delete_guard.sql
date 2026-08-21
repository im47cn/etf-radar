-- 008_close_delete_guard.sql
-- 清仓事件删除护栏（服务端强制）：删除 close 事件会使已平仓交易在复盘/持仓中"复活"，
-- 属于篡改历史事实而非录错回滚。超 7 天的 close 事件禁止删除；7 天内仍可删（录错纠正窗口）。
-- 在 Supabase SQL Editor 中执行（一次性）。

CREATE OR REPLACE FUNCTION enforce_close_delete_guard() RETURNS trigger AS $$
BEGIN
  IF OLD.side = 'close' AND OLD.trade_date < (now() AT TIME ZONE 'Asia/Shanghai')::date - 7 THEN
    RAISE EXCEPTION 'CLOSE_EVENT_LOCKED: 清仓事件超过 7 天不可删除（删除会使已平仓交易在复盘中复活）'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trg_trades_close_delete_guard ON trades;
CREATE TRIGGER trg_trades_close_delete_guard
  BEFORE DELETE ON trades
  FOR EACH ROW EXECUTE FUNCTION enforce_close_delete_guard();
