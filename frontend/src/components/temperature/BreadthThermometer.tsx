import { useMemo } from 'react';
import type { MarketPoint } from '@/types/marketTemperature';
import { breadthColor, breadthLabel } from '@/lib/breadthColor';

interface Props {
  market: MarketPoint[];
  periodLabel?: string;
}

/** 全市场温度计: 当日站上率大数字 + 冷暖标签 + 迷你趋势线. */
export const BreadthThermometer = ({ market, periodLabel = 'MA20' }: Props) => {
  const latest = useMemo(() => {
    for (let i = market.length - 1; i >= 0; i--) {
      if (market[i].rate != null) return market[i];
    }
    return undefined;
  }, [market]);

  const rate = latest?.rate ?? null;
  const spark = useMemo(() => buildSparkline(market), [market]);

  return (
    <div className="flex items-center gap-6 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col items-center">
        <div
          className="flex h-24 w-24 items-center justify-center rounded-full text-3xl font-bold text-gray-800"
          style={{ backgroundColor: breadthColor(rate) }}
        >
          {rate != null ? `${rate.toFixed(1)}%` : '—'}
        </div>
        <div className="mt-2 text-sm text-gray-600">
          全市场 · {breadthLabel(rate)}
        </div>
      </div>
      <div className="flex-1">
        <div className="mb-1 text-xs text-gray-400">
          近 {market.length} 交易日 · 个股 {periodLabel} 站上率
        </div>
        {spark}
        <div className="mt-1 flex justify-between text-[10px] text-gray-400">
          <span>{market[0]?.date}</span>
          <span>{latest?.date}</span>
        </div>
      </div>
    </div>
  );
};

function buildSparkline(market: MarketPoint[]) {
  const W = 240;
  const H = 44;
  const pts = market.map((p, i) => ({ x: i, y: p.rate }));
  const xs = (i: number) => (market.length <= 1 ? 0 : (i / (market.length - 1)) * W);
  const ys = (v: number) => H - (Math.max(0, Math.min(100, v)) / 100) * H;
  const path = pts
    .filter((p) => p.y != null)
    .map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${xs(p.x).toFixed(1)} ${ys(p.y as number).toFixed(1)}`)
    .join(' ');
  return (
    <svg width={W} height={H} className="overflow-visible">
      <line x1={0} y1={ys(50)} x2={W} y2={ys(50)} stroke="#e5e7eb" strokeDasharray="2 2" />
      <path d={path} fill="none" stroke="#3b82f6" strokeWidth={1.5} />
    </svg>
  );
}
