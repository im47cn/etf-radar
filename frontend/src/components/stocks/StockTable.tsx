import { useState } from 'react';
import type { AggregatedStock } from '@/types/holdings';
import { cn } from '@/lib/utils';
import { compareLeader } from '@/lib/stocks/leaderRank';
import { StrengthBadge } from './StrengthBadge';
import { RSIBadge } from './RSIBadge';
import { VolumeRatioBadge } from './VolumeRatioBadge';
import { MiniKlineChart } from './MiniKlineChart';

interface Props {
  stocks: AggregatedStock[];
}

const formatPct = (n: number | null): string => {
  if (n === null || Number.isNaN(n)) return '—';
  const pct = n * 100;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
};

const formatWeight = (w: number): string => `${w.toFixed(1)}%`;

const formatPrice = (n: number | null): string => {
  if (n === null || Number.isNaN(n)) return '—';
  return n.toFixed(2);
};

// 默认排序：leader desc → strength_60d desc → cumulativeWeight desc
function sortByLeaderThenStrength(stocks: AggregatedStock[]): AggregatedStock[] {
  return [...stocks].sort((a, b) => {
    const la = a.indicators?.leader ?? '';
    const lb = b.indicators?.leader ?? '';
    const leaderDiff = compareLeader(lb, la);
    if (leaderDiff !== 0) return leaderDiff;
    const sa = a.indicators?.strength_60d ?? -1;
    const sb = b.indicators?.strength_60d ?? -1;
    if (sb !== sa) return sb - sa;
    return b.cumulativeWeight - a.cumulativeWeight;
  });
}

export const StockTable = ({ stocks }: Props) => {
  const sorted = sortByLeaderThenStrength(stocks);
  const [hoverCode, setHoverCode] = useState<string | null>(null);

  return (
    <div className="relative">
      <table className="w-full text-sm border-collapse">
        <thead className="bg-gray-100 text-xs text-gray-600">
          <tr>
            <th className="px-2 py-2 text-center w-12">#</th>
            <th className="px-2 py-2 text-center w-12">龙头</th>
            <th className="px-2 py-2 text-left">代码</th>
            <th className="px-2 py-2 text-left">名称</th>
            <th className="px-2 py-2 text-left">关联 ETF</th>
            <th className="px-2 py-2 text-right">权重</th>
            <th className="px-2 py-2 text-right">收盘</th>
            <th className="px-2 py-2 text-right">今日</th>
            <th className="px-2 py-2 text-center">60d</th>
            <th className="px-2 py-2 text-center">20d</th>
            <th className="px-2 py-2 text-center">RSI</th>
            <th className="px-2 py-2 text-center">量比</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, idx) => {
            const r1d = s.spot?.r_1d ?? null;
            const ind = s.indicators;
            return (
              <tr
                key={s.code}
                className="border-b hover:bg-gray-50 relative"
                onMouseEnter={() => setHoverCode(s.code)}
                onMouseLeave={() => setHoverCode(prev => (prev === s.code ? null : prev))}
              >
                <td className="px-2 py-2 text-center text-gray-500">{idx + 1}</td>
                <td className="px-2 py-2 text-center text-sm">{ind?.leader ?? ''}</td>
                <td className="px-2 py-2 font-mono">{s.code}</td>
                <td className="px-2 py-2">{s.name}</td>
                <td className="px-2 py-2">
                  <div className="flex flex-wrap gap-1">
                    {s.sourceEtfs.map(etf => (
                      <span key={etf} className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono">
                        {etf}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{formatWeight(s.cumulativeWeight)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatPrice(s.spot?.close ?? null)}</td>
                <td className={cn(
                  'px-2 py-2 text-right tabular-nums',
                  r1d === null ? 'text-gray-400' : r1d >= 0 ? 'text-red-600' : 'text-green-600',
                )}>{formatPct(r1d)}</td>
                <td className="px-2 py-2 text-center">
                  <StrengthBadge value={ind?.strength_60d ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <StrengthBadge value={ind?.strength_20d ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <RSIBadge value={ind?.rsi_14 ?? null} />
                </td>
                <td className="px-2 py-2 text-center">
                  <VolumeRatioBadge value={ind?.vol_ratio ?? null} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {hoverCode && (
        <div
          className="hidden md:block absolute right-0 top-0 z-10 pointer-events-none"
          aria-label={`${hoverCode} K 线浮层`}
        >
          <MiniKlineChart code={hoverCode} />
        </div>
      )}
    </div>
  );
};
