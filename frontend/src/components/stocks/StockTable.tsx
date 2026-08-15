import { useState } from 'react';
import { ChartCard } from '@/components/ChartCard';
import type { AggregatedStock } from '@/types/holdings';
import { cn } from '@/lib/utils';
import { compareLeader } from '@/lib/stocks/leaderRank';
import { StrengthBadge } from './StrengthBadge';
import { RSIBadge } from './RSIBadge';
import { VolumeRatioBadge } from './VolumeRatioBadge';
import { MiniKlineChart } from './MiniKlineChart';
import { useSubscription } from '@/lib/subscription/useSubscription';

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

const formatVolAnn = (n: number | null): string =>
  n === null || Number.isNaN(n) ? '—' : `${(n * 100).toFixed(0)}%`;

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
  // 前瞻波动是会员风控维度: 非会员列内锁定引导升级 (同 HoldingsList 免费 5 支先例)
  const { state: subState } = useSubscription();
  const isMember = subState === 'member';

  return (
    <ChartCard
      title="成分股明细"
      subtitle="按龙头 → 60日强度 → 权重排序 · 悬停看 K 线"
      helpTitle="成分股明细 · 读法"
      help={
        <>
          <p>列：权重 / 现价 / 涨跌 / L2 行业 / 龙头标签 / 60日·20日强度 / RSI / 量比 / 前瞻波动。</p>
          <p><strong>前瞻波动</strong>（🔒 会员）：GARCH(1,1) 预测的未来 60 日年化波动。个股 ARCH 普适（5 年 99.9%）使其有统计基础；用于仓位/风控参考（&gt;60% 标红），<strong>不预测方向</strong>。</p>
          <p>排序：龙头(⭐⭐⭐优先) → 60日强度 → 累计权重；悬停行右侧浮 mini K 线。</p>
          <p><strong>误读</strong>：持仓按季度披露有延迟；权重是 ETF 持仓占比，非个股市值。</p>
        </>
      }
    >
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
            <th className="px-2 py-2 text-center">前瞻波动</th>
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
                <td className={cn(
                  'px-2 py-2 text-center tabular-nums text-xs',
                  !isMember ? 'text-gray-400' : (ind?.vol_forecast_ann ?? 0) > 0.6 ? 'text-red-600' : 'text-gray-700',
                )} title={isMember ? 'GARCH(1,1) 预测未来 60 日年化波动（风控参考，不预测方向）' : '会员可见：GARCH 前瞻波动率'}>
                  {!isMember ? '🔒' : formatVolAnn(ind?.vol_forecast_ann ?? null)}
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
    </ChartCard>
  );
};
