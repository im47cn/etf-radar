/* eslint-disable react-refresh/only-export-components -- aggregateReviews 是统计卡配套纯函数, 供单测直接验证 */
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useTrades } from '@/hooks/useTrades';
import { getReviewAggregates, listReviews } from '@/lib/trading/api';
import { Skeleton } from '@/components/ui/skeleton';
import { ReviewsList, reviewPnl, fmtR } from './ReviewsList';
import type { ReviewAggregatesRow, TradeReview } from '@/lib/trading/types';

export interface ReviewAggregates {
  /** 复盘条数 */
  n: number;
  /** 胜率：实现盈亏 > 0 占比（分母为携带 pnl 的行，与后端 win_rate 口径一致） */
  winRate: number | null;
  /** 平均可得 R */
  avgR: number | null;
  /** 盈亏比 = Σ盈利 ÷ |Σ亏损|（无亏损样本 → null） */
  profitFactor: number | null;
  /** 期望 = 平均实现盈亏（元） */
  expectancy: number | null;
}

/** 客户端聚合（与后端 AggregateStats 口径对齐）：for 循环逐行累加（CONVENTIONS coverage 盲区）。 */
export const aggregateReviews = (reviews: TradeReview[]): ReviewAggregates => {
  let n = 0;
  let pnlCount = 0;
  let wins = 0;
  let sumPnl = 0;
  let sumWin = 0;
  let sumLoss = 0;
  let rCount = 0;
  let sumR = 0;
  for (const r of reviews) {
    n += 1;
    const pnl = reviewPnl(r.events);
    if (pnl != null) {
      pnlCount += 1;
      sumPnl += pnl;
      if (pnl > 0) {
        wins += 1;
        sumWin += pnl;
      } else {
        sumLoss += pnl;
      }
    }
    if (r.result_r != null) {
      rCount += 1;
      sumR += r.result_r;
    }
  }
  return {
    n,
    winRate: pnlCount > 0 ? wins / pnlCount : null,
    avgR: rCount > 0 ? sumR / rCount : null,
    profitFactor: sumLoss < 0 ? sumWin / Math.abs(sumLoss) : null,
    expectancy: pnlCount > 0 ? sumPnl / pnlCount : null,
  };
};

const fmtPct = (v: number | null): string => (v != null ? `${(v * 100).toFixed(1)}%` : '—');
const fmtFactor = (v: number | null): string => (v != null ? v.toFixed(2) : '—');
const fmtYuan = (v: number | null): string =>
  v != null ? `${v > 0 ? '+' : ''}${v.toFixed(0)} 元` : '—';

const StatCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded border bg-white p-3 text-center shadow-sm">
    <div className="text-xs text-gray-500">{label}</div>
    <div className="mt-1 text-lg font-semibold text-gray-800">{value}</div>
  </div>
);

/**
 * 复盘 Tab：trade_reviews 由 Actions 每晚写入（本人只读），此处独立加载
 * （useTrades 只管 trades/settings；reviews 低频且无 realtime 需求）。
 * 会员门内挂载（FeatureGate required=member，见 TradingPage）。
 */
export const ReviewsTab = () => {
  const { user, status } = useAuth();
  const { trades } = useTrades();
  // null = 加载中；[] = 已加载且为空（Actions 尚未跑过）
  const [reviews, setReviews] = useState<TradeReview[] | null>(null);
  // null = 无物化快照（Actions 未跑过/表为空）→ 客户端兜底聚合
  const [materialized, setMaterialized] = useState<ReviewAggregatesRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  const userId = user?.id ?? null;
  useEffect(() => {
    if (status !== 'authenticated') return;
    let cancelled = false;
    listReviews(userId)
      .then((rs) => {
        if (cancelled) return;
        setReviews(rs);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    getReviewAggregates(userId)
      .then((row) => {
        if (!cancelled) setMaterialized(row);
      })
      .catch(() => {
        // 物化快照读失败不阻断页面: 落客户端兜底口径
        if (!cancelled) setMaterialized(null);
      });
    return () => {
      cancelled = true;
    };
  }, [status, userId]);

  const namesByTradeId = useMemo(() => {
    const m = new Map<string, { code: string; name: string }>();
    for (const t of trades) m.set(t.id, { code: t.code, name: t.name });
    return m;
  }, [trades]);

  // 优先 Actions 物化快照 (单一权威口径); 无快照时客户端兜底聚合。
  // 物化 stats 为后端 snake_case, 在此映射为本组件 camelCase 接口。
  const fallbackAgg = useMemo(() => aggregateReviews(reviews ?? []), [reviews]);
  const agg: ReviewAggregates =
    materialized != null
      ? {
          n: materialized.stats.n,
          winRate: materialized.stats.win_rate,
          avgR: materialized.stats.avg_r,
          profitFactor: materialized.stats.profit_factor,
          expectancy: materialized.stats.expectancy,
        }
      : fallbackAgg;
  const nLabel = agg.n > 0 ? `${agg.n} 笔已复盘` : '';
  const statsSource = materialized != null ? '服务端统一口径' : '客户端兜底口径';

  return (
    <div className="flex flex-col gap-4">
      {error != null && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          复盘数据加载失败：{error}
        </div>
      )}

      {reviews == null && error == null ? (
        <div className="flex flex-col gap-4" aria-busy="true" aria-label="加载中">
          <Skeleton className="h-20" />
          <Skeleton className="h-48" />
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-medium text-gray-800">复盘统计</div>
              <div className="text-xs text-gray-400">
                {nLabel}{nLabel !== '' ? ' · ' : ''}{statsSource}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <StatCard label="胜率" value={fmtPct(agg.winRate)} />
              <StatCard label="平均 R" value={fmtR(agg.avgR)} />
              <StatCard label="盈亏比" value={fmtFactor(agg.profitFactor)} />
              <StatCard label="期望（每笔）" value={fmtYuan(agg.expectancy)} />
            </div>
            <p className="text-xs text-gray-400">
              统计口径：胜率按实现盈亏 &gt; 0；盈亏比 = Σ盈利 ÷ |Σ亏损|（无亏损样本显示 —）；
              期望为平均实现盈亏；平均 R 为可得 R 均值。数据不足显示 —。历史统计描述，不构成投资建议。
            </p>
          </div>

          <ReviewsList reviews={reviews ?? []} namesByTradeId={namesByTradeId} />
        </>
      )}
    </div>
  );
};
