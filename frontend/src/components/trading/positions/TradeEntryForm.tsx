import { useState, type FormEvent } from 'react';
import { useTrades } from '@/hooks/useTrades';
import type { TradeSide } from '@/lib/trading/types';
import { TRADE_SIDES, TRADE_SIDE_LABEL } from './sideLabel';
import { validateTradeFields, parseStopAfter } from './tradeValidation';

const inputClass =
  'w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none';

/** 本地时区的 YYYY-MM-DD（toISOString 会按 UTC 切日，跨日错一天）。 */
const todayStr = (): string => {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
};

/**
 * 交易记录录入（记账表单，非操作指令）：记录已发生的 open/add/reduce/close 事实，
 * 写 trades 表并由事件流推导持仓。不触发任何买卖建议（合规立场 §0）。
 */
export const TradeEntryForm = () => {
  const { addTrade } = useTrades();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [side, setSide] = useState<TradeSide>('open');
  const [date, setDate] = useState(todayStr());
  const [price, setPrice] = useState('');
  const [shares, setShares] = useState('');
  const [stopAfter, setStopAfter] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaved(false);

    const errs = validateTradeFields({ code, name, tradeDate: date, price, shares, stopAfter });
    setErrors(errs);
    if (errs.length > 0) return;

    setSubmitting(true);
    const r = await addTrade({
      code: code.trim(),
      name: name.trim(),
      side,
      trade_date: date,
      price: Number(price),
      shares: Number(shares),
      stop_after: parseStopAfter(stopAfter),
    });
    setSubmitting(false);
    if (r.error) {
      setErrors([r.error]);
      return;
    }
    setErrors([]);
    setCode('');
    setName('');
    setPrice('');
    setShares('');
    setStopAfter('');
    setSaved(true);
  };

  return (
    <form onSubmit={onSubmit} className="rounded-lg border bg-white p-4 shadow-sm" aria-label="交易记录录入">
      <div className="text-sm font-medium text-gray-800">交易记录录入</div>
      <div className="mt-1 text-xs text-gray-500">
        记录已发生的交易事实（开仓/加仓/减仓/清仓），用于持仓汇总与复盘统计；本表单为记账工具，不构成操作指令。
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          代码
          <input
            className={inputClass}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="600519"
            inputMode="numeric"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          名称
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="贵州茅台"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          事件类型
          <select
            className={inputClass}
            value={side}
            onChange={(e) => setSide(e.target.value as TradeSide)}
          >
            {TRADE_SIDES.map((s) => (
              <option key={s} value={s}>{TRADE_SIDE_LABEL[s]}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          交易日期
          <input
            type="date"
            className={inputClass}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          成交价（元）
          <input
            className={inputClass}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="17.10"
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          股数
          <input
            className={inputClass}
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            placeholder="100"
            inputMode="numeric"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          该笔后止损位（可选）
          <input
            className={inputClass}
            value={stopAfter}
            onChange={(e) => setStopAfter(e.target.value)}
            placeholder="15.73"
            inputMode="decimal"
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:bg-gray-300"
          >
            {submitting ? '记入中...' : '记入流水'}
          </button>
        </div>
      </div>

      {errors.length > 0 && (
        <div role="alert" className="mt-2 text-xs text-red-600">
          {errors.join('；')}
        </div>
      )}
      {saved && <div className="mt-2 text-xs text-green-600">✓ 已记入流水</div>}
    </form>
  );
};
