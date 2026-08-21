import { useState, type FormEvent } from 'react';
import { useTrades } from '@/hooks/useTrades';
import type { Trade, TradeSide } from '@/lib/trading/types';
import { TRADE_SIDES, TRADE_SIDE_LABEL } from './sideLabel';
import { validateTradeFields, parseStopAfter } from './tradeValidation';

const inputClass =
  'w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none';

/**
 * 事件行内编辑（修正错录）：预填当前值，保存 = 删旧插新，
 * 由事件流重放刷新持仓。reason 不在此暴露（保留原值）。
 * 清仓事件超 7 天由 TradesLog 同口径禁用入口（008 历史事实保护）。
 */
export const TradeEditForm = ({ trade, onDone }: { trade: Trade; onDone: () => void }) => {
  const { editTrade } = useTrades();
  const [code, setCode] = useState(trade.code);
  const [name, setName] = useState(trade.name);
  const [side, setSide] = useState<TradeSide>(trade.side);
  const [date, setDate] = useState(trade.trade_date);
  const [price, setPrice] = useState(String(trade.price));
  const [shares, setShares] = useState(String(trade.shares));
  const [stopAfter, setStopAfter] = useState(trade.stop_after != null ? String(trade.stop_after) : '');
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const errs = validateTradeFields({ code, name, tradeDate: date, price, shares, stopAfter });
    setErrors(errs);
    if (errs.length > 0) return;

    setSubmitting(true);
    const r = await editTrade(trade.id, {
      code: code.trim(),
      name: name.trim(),
      side,
      trade_date: date,
      price: Number(price),
      shares: Number(shares),
      stop_after: parseStopAfter(stopAfter),
      reason: trade.reason,
    });
    setSubmitting(false);
    if (r.error) {
      setErrors([r.error]);
      return;
    }
    onDone();
  };

  return (
    <form onSubmit={onSubmit} className="mt-2 w-full rounded border border-blue-200 bg-blue-50/50 p-3" aria-label="交易记录编辑">
      <div className="text-xs font-medium text-gray-700">修正该笔交易</div>
      <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          代码
          <input className={inputClass} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          名称
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          事件类型
          <select className={inputClass} value={side} onChange={(e) => setSide(e.target.value as TradeSide)}>
            {TRADE_SIDES.map((s) => (
              <option key={s} value={s}>{TRADE_SIDE_LABEL[s]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          交易日期
          <input type="date" className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          成交价（元）
          <input className={inputClass} value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          股数
          <input className={inputClass} value={shares} onChange={(e) => setShares(e.target.value)} inputMode="numeric" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          该笔后止损位（可选）
          <input className={inputClass} value={stopAfter} onChange={(e) => setStopAfter(e.target.value)} inputMode="decimal" />
        </label>
        <div className="flex items-end gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:bg-gray-300"
          >
            {submitting ? '保存中...' : '保存修改'}
          </button>
          <button
            type="button"
            onClick={onDone}
            disabled={submitting}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-50"
          >
            取消
          </button>
        </div>
      </div>

      {errors.length > 0 && (
        <div role="alert" className="mt-2 text-xs text-red-600">
          {errors.join('；')}
        </div>
      )}
      <div className="mt-1 text-[10px] text-gray-400">
        保存将删除原记录并以修改后内容重新记入（事件流重放自动更新持仓）；清仓事件超 7 天后不可修改。
      </div>
    </form>
  );
};
