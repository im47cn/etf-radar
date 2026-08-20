/* eslint-disable react-refresh/only-export-components -- calcPosition 是 PositionCalculator 的配套纯函数, 供单测直接验证 */
import { useState } from 'react';
import type { TradingRegime } from '@/types/trading';

/**
 * 仓位计算器 (spec §1.7): 风险预算法纯算术展示.
 * 输出为计算结果而非操作指令 (合规立场 §0).
 */

export interface PositionCalcInput {
  /** 账户权益 (元) */
  equity: number;
  /** 入场价 */
  entry: number;
  /** 止损价 (做多方向应在入场价下方) */
  stop: number;
  /** 单笔风险占权益百分比, 默认 0.75 */
  riskPct: number;
  /** 单票市值上限占权益百分比, 默认 20 */
  maxPositionPct: number;
}

export interface PositionCalcResult {
  /** 单笔风险额 = 权益 × riskPct% */
  riskAmount: number;
  /** 每股风险 = 入场价 − 止损价 */
  perShareRisk: number;
  /** 风险预算允许股数 */
  sharesByRisk: number;
  /** 市值上限允许股数 */
  sharesByCap: number;
  /** 最终股数 = 两口径取小 */
  shares: number;
  marketValue: number;
  /** 市值占权益 % */
  positionPct: number;
  /** 约束口径 */
  binding: 'risk' | 'cap';
}

/** 纯计算: 任一输入非正 / 入场价 ≤ 止损价 → null (输入无效). */
export const calcPosition = (input: PositionCalcInput): PositionCalcResult | null => {
  const { equity, entry, stop, riskPct, maxPositionPct } = input;
  if (!(equity > 0) || !(entry > 0) || !(stop > 0)) return null;
  if (!(riskPct > 0) || !(maxPositionPct > 0)) return null;
  const perShareRisk = entry - stop;
  if (!(perShareRisk > 0)) return null;

  const riskAmount = (equity * riskPct) / 100;
  const sharesByRisk = Math.floor(riskAmount / perShareRisk);
  const sharesByCap = Math.floor((equity * maxPositionPct) / 100 / entry);
  const shares = Math.min(sharesByRisk, sharesByCap);
  const marketValue = shares * entry;
  return {
    riskAmount,
    perShareRisk,
    sharesByRisk,
    sharesByCap,
    shares,
    marketValue,
    positionPct: (marketValue / equity) * 100,
    binding: shares === sharesByCap && sharesByCap < sharesByRisk ? 'cap' : 'risk',
  };
};

const parsePositive = (s: string): number | null => {
  const v = Number(s.trim());
  return s.trim() !== '' && v > 0 ? v : null;
};

const inputClass =
  'w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none';

/** 环境档位联动提示 (事实性展示, 非指令). */
const regimeHint = (regime: TradingRegime | null): string => {
  if (regime === 'offense') return '当前环境档位为进攻：按所选风险预算口径计算。';
  if (regime === 'neutral') return '当前环境档位为中性：附风险预算减半口径（单笔风险 ×0.5）供对照。';
  if (regime === 'defense') return '当前环境档位为防守：以下仅为算术计算展示，无操作含义。';
  return '环境档位数据缺失：按所选风险预算口径计算。';
};

export const PositionCalculator = ({ regime }: { regime: TradingRegime | null }) => {
  const [equityStr, setEquityStr] = useState('');
  const [entryStr, setEntryStr] = useState('');
  const [stopStr, setStopStr] = useState('');
  const [riskPctStr, setRiskPctStr] = useState('0.75');
  const [maxPosPctStr, setMaxPosPctStr] = useState('20');

  const equity = parsePositive(equityStr);
  const entry = parsePositive(entryStr);
  const stop = parsePositive(stopStr);
  const riskPct = parsePositive(riskPctStr);
  const maxPositionPct = parsePositive(maxPosPctStr);

  /** 全参非空才计算; riskScale 用于中性档减半口径 (单笔风险 ×0.5). */
  const tryCalc = (
    e: number | null,
    en: number | null,
    st: number | null,
    rp: number | null,
    mp: number | null,
    riskScale = 1,
  ): PositionCalcResult | null =>
    e != null && en != null && st != null && rp != null && mp != null
      ? calcPosition({ equity: e, entry: en, stop: st, riskPct: rp * riskScale, maxPositionPct: mp })
      : null;

  const allFilled = equity != null && entry != null && stop != null;
  const result = tryCalc(equity, entry, stop, riskPct, maxPositionPct);
  const halfResult = regime === 'neutral' ? tryCalc(equity, entry, stop, riskPct, maxPositionPct, 0.5) : null;

  const anyInput = equityStr !== '' || entryStr !== '' || stopStr !== '';
  const invalidDir = allFilled && result == null;
  // 约束口径文案提 const: JSX 内三元是 coverage 盲区
  const bindingLabel = result != null && result.binding === 'cap' ? '受市值上限约束' : '受风险预算约束';

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <div className="text-sm font-medium text-gray-800">仓位计算器（风险预算法）</div>
      <div className="mt-1 text-xs text-gray-500">
        按单笔风险额 ÷ 每股风险得出股数，再与单票市值上限取小。纯算术展示，不构成操作指令。
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          权益（元）
          <input className={inputClass} inputMode="decimal" value={equityStr} onChange={(e) => setEquityStr(e.target.value)} placeholder="100000" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          入场价
          <input className={inputClass} inputMode="decimal" value={entryStr} onChange={(e) => setEntryStr(e.target.value)} placeholder="17.10" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          止损价
          <input className={inputClass} inputMode="decimal" value={stopStr} onChange={(e) => setStopStr(e.target.value)} placeholder="15.73" />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          单笔风险 %
          <input className={inputClass} inputMode="decimal" value={riskPctStr} onChange={(e) => setRiskPctStr(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-600">
          单票市值上限 %
          <input className={inputClass} inputMode="decimal" value={maxPosPctStr} onChange={(e) => setMaxPosPctStr(e.target.value)} />
        </label>
      </div>

      <p className="mt-3 text-xs text-gray-500">{regimeHint(regime)}</p>

      {result == null ? (
        <p className="mt-2 text-xs text-gray-400" role="status">
          {invalidDir
            ? '入场价不高于止损价：每份风险非正，请检查输入方向（做多止损应低于入场价）。'
            : anyInput
              ? '请输入有效的正数（权益 / 入场价 / 止损价 / 参数）。'
              : '输入权益、入场价、止损价后显示计算结果。'}
        </p>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-3 rounded-md bg-gray-50 p-3 text-xs sm:grid-cols-4">
          <div>
            <div className="text-gray-500">计算股数</div>
            <div className="text-lg font-semibold text-gray-900">{result.shares} 股</div>
            <div className="text-gray-400">{bindingLabel}</div>
          </div>
          <div>
            <div className="text-gray-500">单笔风险额</div>
            <div className="text-gray-800">{result.riskAmount.toFixed(0)} 元</div>
            <div className="text-gray-400">每股风险 {result.perShareRisk.toFixed(2)} 元</div>
          </div>
          <div>
            <div className="text-gray-500">投入市值</div>
            <div className="text-gray-800">{result.marketValue.toFixed(0)} 元</div>
            <div className="text-gray-400">占权益 {result.positionPct.toFixed(1)}%</div>
          </div>
          <div>
            <div className="text-gray-500">口径对照</div>
            <div className="text-gray-800">风险预算 {result.sharesByRisk} 股</div>
            <div className="text-gray-400">市值上限 {result.sharesByCap} 股</div>
          </div>
          {halfResult != null && (
            <div className="col-span-2 sm:col-span-4 border-t border-gray-200 pt-2 text-gray-500">
              中性档减半口径（单笔风险 ×0.5）：{halfResult.shares} 股。
            </div>
          )}
        </div>
      )}
    </div>
  );
};
