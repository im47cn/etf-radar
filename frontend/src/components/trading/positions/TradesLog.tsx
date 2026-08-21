import { useState } from 'react';
import { useTrades } from '@/hooks/useTrades';
import type { Trade } from '@/lib/trading/types';
import { TRADE_SIDE_LABEL } from './sideLabel';
import { isCloseDeleteLocked } from './closeGuard';

const sideBadgeClass = (side: Trade['side']): string =>
  side === 'open' || side === 'add'
    ? 'bg-red-900/50 text-red-300'
    : 'bg-green-900/50 text-green-300';

/**
 * 交易事件流（最新在前）。删除仅用于录错回滚：两步行内确认
 * （「删除」→「确认删除」），确认后 removeTrade 并由事件流重放回滚影响。
 */
export const TradesLog = () => {
  const { trades, removeTrade } = useTrades();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (trades.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-500">
        暂无交易记录：在上方「交易记录录入」记账后，事件按时间顺序在此列出。
      </div>
    );
  }

  // 最新在前（事件流推导用升序，展示用倒序副本，不改 context 数据）
  const rows = [...trades].reverse();

  const onRemove = async (id: string) => {
    if (confirmId !== id) {
      setConfirmId(id);
      setError(null);
      return;
    }
    setBusyId(id);
    const r = await removeTrade(id);
    setBusyId(null);
    if (r.error) {
      setError(r.error);
      return;
    }
    setConfirmId(null);
  };

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-800">交易事件流</div>
      <ul className="mt-2 flex flex-col divide-y divide-gray-100">
        {rows.map((t) => {
          const badge = TRADE_SIDE_LABEL[t.side];
          const badgeClass = sideBadgeClass(t.side);
          const stopLabel = t.stop_after != null ? `止损位 ${t.stop_after.toFixed(2)}` : '';
          const isConfirming = confirmId === t.id;
          const isBusy = busyId === t.id;
          const isLocked = isCloseDeleteLocked(t);
          const btnLabel = isConfirming ? '确认删除' : '删除';
          const btnClass = isConfirming
            ? 'rounded bg-red-600 px-2 py-0.5 text-xs text-white'
            : 'rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-50';
          return (
            <li key={t.id} className="flex flex-wrap items-center gap-2 py-1.5 text-xs text-gray-700">
              <span className="font-mono text-gray-500">{t.trade_date}</span>
              <span className="font-mono">{t.code}</span>
              <span>{t.name}</span>
              <span className={`rounded px-1.5 py-0.5 ${badgeClass}`}>{badge}</span>
              <span>{t.price.toFixed(2)} × {t.shares} 股</span>
              {stopLabel !== '' && <span className="text-gray-500">{stopLabel}</span>}
              <span className="ml-auto">
                {isLocked ? (
                  <span
                    className="rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-300"
                    title="清仓事件超过 7 天不可删除：删除会使已平仓交易在复盘中复活（历史事实保护）"
                  >
                    已锁定
                  </span>
                ) : (
                  <button type="button" className={btnClass} disabled={isBusy} onClick={() => onRemove(t.id)}>
                    {isBusy ? '删除中...' : btnLabel}
                  </button>
                )}
                {isConfirming && t.side === 'close' && (
                  <span className="text-[10px] text-amber-600">删除清仓事件会使该交易回到持仓列表</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="mt-1 text-[10px] text-gray-400">删除仅用于录错回滚：删除一笔事件后，持仓将按剩余事件流重新推导。清仓事件超过 7 天自动锁定（删除会使已平仓交易复活）。</div>
      {error && (
        <div role="alert" className="mt-2 text-xs text-red-600">
          {error}
        </div>
      )}
    </div>
  );
};
