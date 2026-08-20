/* eslint-disable react-refresh/only-export-components -- fmt/窄化 helpers 与组件同文件, ReviewsTab 复用 (目录所有权内) */
import type { TradeReview } from '@/lib/trading/types';

/** 复盘事件 jsonb 结构（M4 review.py 写入）：{ dimensions: 四维布尔, open_stop, pnl }。 */

// 纪律四维（spec §2.5：入场在买区/止损执行/退出响应/仓位合规，各 25 分）
export const REVIEW_DIM_ORDER = [
  'entry_in_buy_zone',
  'stop_discipline',
  'exit_responsiveness',
  'position_compliance',
] as const;

export const REVIEW_DIM_LABEL: Record<string, string> = {
  entry_in_buy_zone: '入场在买区',
  stop_discipline: '止损纪律',
  exit_responsiveness: '退出响应',
  position_compliance: '仓位合规',
};

const asRecord = (v: unknown): Record<string, unknown> | null =>
  v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;

/** events.dimensions 窄化：非对象/缺省 → null。 */
export const reviewDimensions = (events: TradeReview['events']): Record<string, unknown> | null => {
  const ev = asRecord(events);
  if (ev == null) return null;
  return asRecord(ev.dimensions);
};

/** events.pnl 窄化（胜率/期望口径与后端一致：按实现盈亏）。 */
export const reviewPnl = (events: TradeReview['events']): number | null => {
  const ev = asRecord(events);
  if (ev == null) return null;
  const pnl = ev.pnl;
  return typeof pnl === 'number' && Number.isFinite(pnl) ? pnl : null;
};

export const fmtScore = (v: number | null): string => (v != null ? String(v) : '—');
export const fmtR = (v: number | null): string =>
  v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}R` : '—';
export const fmtPctSigned = (v: number | null): string =>
  v != null ? `${v > 0 ? '+' : ''}${v.toFixed(2)}%` : '—';

interface ReviewsListProps {
  reviews: TradeReview[];
  /** trade_id → 代码/名称（来自 trades 表；事件流已删除的记录查不到 → '—'） */
  namesByTradeId: Map<string, { code: string; name: string }>;
}

/** trade_reviews 列表（本人只读，Actions 每晚写入）。事实性评分展示。 */
export const ReviewsList = ({ reviews, namesByTradeId }: ReviewsListProps) => {
  if (reviews.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500">
        复盘评分将在每晚交易数据管线运行后生成：已平仓交易的纪律分（0-100）、R 倍数、
        MAE 与事件明细将在此展示。
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-800">逐笔复盘</div>
      <ul className="mt-2 flex flex-col divide-y divide-gray-100">
        {reviews.map((r) => {
          const n = namesByTradeId.get(r.trade_id);
          const codeLabel = n != null ? n.code : '—';
          const nameLabel = n != null ? n.name : '';
          const dims = reviewDimensions(r.events);
          return (
            <li key={r.id} className="flex flex-col gap-1 py-2 text-xs text-gray-700">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-gray-500">{r.review_date}</span>
                <span className="font-mono">{codeLabel}</span>
                <span>{nameLabel}</span>
                <span>纪律分 <strong className="text-gray-900">{fmtScore(r.discipline_score)}</strong></span>
                <span>结果 <strong className="text-gray-900">{fmtR(r.result_r)}</strong></span>
                <span>MAE <span className="text-gray-500">{fmtPctSigned(r.mae_pct)}</span></span>
              </div>
              {dims != null && (
                <div className="flex flex-wrap gap-2">
                  {REVIEW_DIM_ORDER.map((k) => {
                    const ok = dims[k] === true;
                    const dimLabel = REVIEW_DIM_LABEL[k] ?? k;
                    const dimClass = ok ? 'text-green-600' : 'text-gray-400';
                    return (
                      <span key={k} className={dimClass}>
                        {ok ? '✓' : '✗'} {dimLabel}
                      </span>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
};
