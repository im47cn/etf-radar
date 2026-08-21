-- 007_review_aggregates.sql
-- 复盘聚合统计物化：Actions 每晚按用户计算 aggregate_stats 后写入（幂等覆写），
-- 前端只读物化结果（消除前后端双实现的口径漂移，客户端聚合降级为兜底）。
-- 在 Supabase SQL Editor 中执行（一次性；依赖 001 的 set_updated_at()）。

CREATE TABLE IF NOT EXISTS review_aggregates (
  user_id     uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  as_of       date        NOT NULL,                  -- 快照基准日
  stats       jsonb       NOT NULL,                  -- AggregateStats: {n,win_rate,avg_r,profit_factor,expectancy,max_drawdown,by_regime}
  computed_at timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_review_aggregates_updated ON review_aggregates;
CREATE TRIGGER trg_review_aggregates_updated
  BEFORE UPDATE ON review_aggregates
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE review_aggregates ENABLE ROW LEVEL SECURITY;

-- 同 trade_reviews: 本人仅 SELECT；写入仅 Actions (service_role)。
DROP POLICY IF EXISTS review_aggregates_own_select ON review_aggregates;
CREATE POLICY review_aggregates_own_select ON review_aggregates
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());
