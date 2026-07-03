-- 003_membership.sql
-- 会员订阅 MVP：subscriptions / bind_codes / watchlist / webhook_events 四表 + RLS + RPC
-- 在 Supabase SQL Editor 中执行（一次性）
--
-- 依赖 001_user_holdings.sql 已创建的通用触发器函数 set_updated_at()。
-- 若尚未执行 001，请先执行之，或取消下面这段兜底定义的注释：
-- CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
-- BEGIN NEW.updated_at = now(); RETURN NEW; END;
-- $$ LANGUAGE plpgsql;

-- ========== subscriptions ==========
-- 订阅状态。写入只由 Edge Function 以 service_role key 完成（绕过 RLS），
-- 前端仅有 SELECT 策略，杜绝伪造会员。
CREATE TABLE IF NOT EXISTS subscriptions (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  plan                text        NOT NULL CHECK (plan IN ('monthly','yearly')),
  status              text        NOT NULL DEFAULT 'inactive' CHECK (status IN ('active','inactive','expired')),
  current_period_end  timestamptz,                 -- 到期时间；会员有效性以此为准
  source              text        NOT NULL DEFAULT 'afdian',
  afdian_trade_no     text,                         -- 最近一笔订单号，幂等去重用
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user
  ON subscriptions (user_id);

DROP TRIGGER IF EXISTS trg_subscriptions_updated ON subscriptions;
CREATE TRIGGER trg_subscriptions_updated
  BEFORE UPDATE ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- 仅本人可读；无 INSERT/UPDATE/DELETE 策略 → authenticated 无法写。
DROP POLICY IF EXISTS subscriptions_own_select ON subscriptions;
CREATE POLICY subscriptions_own_select ON subscriptions
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- ========== bind_codes ==========
-- 账号打通：用户在爱发电订单留言填写此短码，webhook 据此匹配 Supabase user。
CREATE TABLE IF NOT EXISTS bind_codes (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  code        text        NOT NULL UNIQUE,          -- 8 位 base32 短码
  consumed    boolean     NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bind_codes_user
  ON bind_codes (user_id);

ALTER TABLE bind_codes ENABLE ROW LEVEL SECURITY;

-- 仅本人可读；生成走 issue_bind_code() RPC（SECURITY DEFINER），前端不直接 INSERT。
DROP POLICY IF EXISTS bind_codes_own_select ON bind_codes;
CREATE POLICY bind_codes_own_select ON bind_codes
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- ========== watchlist ==========
-- 会员自选盯盘项。RLS 保证本人数据隔离；"仅会员可写"由 add_watchlist() RPC 硬约束。
CREATE TABLE IF NOT EXISTS watchlist (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  item_type   text        NOT NULL CHECK (item_type IN ('theme','etf')),
  item_key    text        NOT NULL,                 -- 主题 id 或 ETF code
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, item_type, item_key)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user
  ON watchlist (user_id);

ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;

-- 本人读写（同 holdings_own 风格）。注意：写入建议走 add_watchlist() RPC，
-- 以便在服务端强制会员校验；直连 INSERT 只受本人隔离约束（用于 remove 走 DELETE）。
DROP POLICY IF EXISTS watchlist_own ON watchlist;
CREATE POLICY watchlist_own ON watchlist
  FOR ALL TO authenticated
  USING      (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- ========== webhook_events ==========
-- afdian webhook 审计表：所有处理路径（成功/验签失败/无绑定码/未匹配用户）都落一条，
-- 满足"不静默吞错"。无 authenticated 策略 → 仅 service_role 可读写。
CREATE TABLE IF NOT EXISTS webhook_events (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source        text        NOT NULL DEFAULT 'afdian',
  out_trade_no  text,                               -- 订单号，便于排查/去重
  outcome       text        NOT NULL,               -- activated / dup / bad_sign / no_bind_code / no_user / error
  raw_payload   jsonb,                              -- 原始回调体
  note          text,                               -- 处理结论/异常信息
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_trade
  ON webhook_events (out_trade_no);

ALTER TABLE webhook_events ENABLE ROW LEVEL SECURITY;
-- 故意不创建任何策略 → authenticated 一律无权限；service_role 绕过 RLS。

-- ========== RPC: issue_bind_code ==========
-- 复用本人未 consumed 的有效码；否则生成新的 8 位 base32 短码。
-- SECURITY DEFINER 以绕过 bind_codes 无 INSERT 策略的限制，但只操作 auth.uid() 本人数据。
CREATE OR REPLACE FUNCTION issue_bind_code()
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid       uuid := auth.uid();
  existing  text;
  new_code  text;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'NOT_AUTHENTICATED';
  END IF;

  -- 复用本人最近一枚未消费的码
  SELECT code INTO existing
  FROM bind_codes
  WHERE user_id = uid AND consumed = false
  ORDER BY created_at DESC
  LIMIT 1;

  IF existing IS NOT NULL THEN
    RETURN existing;
  END IF;

  -- 生成唯一新码：base32 字母表（去掉易混字符 0/1/8/9/I/L/O/U），8 位。
  LOOP
    SELECT string_agg(
             substr('ABCDEFGHJKMNPQRSTVWXYZ234567',
                    floor(random() * 27)::int + 1, 1), '')
    INTO new_code
    FROM generate_series(1, 8);
    EXIT WHEN NOT EXISTS (SELECT 1 FROM bind_codes WHERE code = new_code);
  END LOOP;

  INSERT INTO bind_codes (user_id, code) VALUES (uid, new_code);
  RETURN new_code;
END;
$$;

REVOKE ALL ON FUNCTION issue_bind_code() FROM public;
GRANT EXECUTE ON FUNCTION issue_bind_code() TO authenticated;

-- ========== RPC: add_watchlist ==========
-- 服务端硬约束"仅会员可用自选"：先校验本人订阅 active 且未过期，否则 RAISE EXCEPTION。
CREATE OR REPLACE FUNCTION add_watchlist(p_item_type text, p_item_key text)
RETURNS watchlist
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid    uuid := auth.uid();
  is_member boolean;
  row    watchlist;
BEGIN
  IF uid IS NULL THEN
    RAISE EXCEPTION 'NOT_AUTHENTICATED';
  END IF;

  IF p_item_type NOT IN ('theme','etf') THEN
    RAISE EXCEPTION 'INVALID_ITEM_TYPE';
  END IF;

  -- 会员校验：status=active 且 current_period_end 在未来
  SELECT EXISTS (
    SELECT 1 FROM subscriptions
    WHERE user_id = uid
      AND status = 'active'
      AND current_period_end IS NOT NULL
      AND current_period_end > now()
  ) INTO is_member;

  IF NOT is_member THEN
    RAISE EXCEPTION 'NOT_A_MEMBER';
  END IF;

  INSERT INTO watchlist (user_id, item_type, item_key)
  VALUES (uid, p_item_type, p_item_key)
  ON CONFLICT (user_id, item_type, item_key) DO UPDATE
    SET item_key = EXCLUDED.item_key   -- no-op 更新以返回既有行
  RETURNING * INTO row;

  RETURN row;
END;
$$;

REVOKE ALL ON FUNCTION add_watchlist(text, text) FROM public;
GRANT EXECUTE ON FUNCTION add_watchlist(text, text) TO authenticated;

-- ========== Realtime（可选） ==========
-- 若希望自选/订阅变更实时刷新，在 Supabase 控制台启用，或执行：
-- ALTER PUBLICATION supabase_realtime ADD TABLE watchlist;
-- ALTER PUBLICATION supabase_realtime ADD TABLE subscriptions;
