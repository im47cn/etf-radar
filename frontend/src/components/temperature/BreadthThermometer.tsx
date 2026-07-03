import { useMemo } from 'react';
import type { MarketPoint } from '@/types/marketTemperature';
import {
  breadthColor,
  breadthLabel,
  breadthLevelColor,
  breadthTextureCss,
  breadthTierPatternId,
  TIERS,
} from '@/lib/breadthColor';

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
          style={{ backgroundColor: breadthColor(rate), ...breadthTextureCss(rate) }}
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
  const n = market.length;
  const xs = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
  const ys = (v: number) => H - (Math.max(0, Math.min(100, v)) / 100) * H;
  const bandW = n <= 1 ? W : W / (n - 1);
  // 逐日温度背景色带: 每天用其站上率对应的冷暖色 + 同档半透明纹理(SVG pattern 双层 rect)
  const bands = market.flatMap((p, i) => {
    if (p.rate == null) return [];
    const left = Math.max(0, xs(i) - bandW / 2);
    const right = Math.min(W, xs(i) + bandW / 2);
    const w = Math.max(0.6, right - left);
    const patternId = breadthTierPatternId(p.rate);
    return [
      // 底层: 纯色
      <rect key={`c${i}`} x={left} y={0} width={w} height={H} fill={breadthLevelColor(p.rate)} />,
      // 上层: 同尺寸半透明斜线纹理(pattern 只含斜线, 底色由下层决定)
      patternId ? (
        <rect key={`t${i}`} x={left} y={0} width={w} height={H} fill={`url(#${patternId})`} />
      ) : null,
    ];
  });
  const path = market
    .map((p, i) => ({ x: i, y: p.rate }))
    .filter((p) => p.y != null)
    .map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${xs(p.x).toFixed(1)} ${ys(p.y as number).toFixed(1)}`)
    .join(' ');
  return (
    <svg
      width="100%"
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="block rounded"
    >
      <defs>
        {/* 4 档半透明斜线 pattern: 只画斜线不含底色, hatch 角度与 HTML 面一致 */}
        {TIERS.map((t) => (
          <pattern
            key={t.key}
            id={`breadth-tex-${t.key}`}
            patternUnits="userSpaceOnUse"
            width={7}
            height={7}
            patternTransform={`rotate(${t.hatch})`}
          >
            <line x1={0} y1={0} x2={0} y2={7} stroke="rgba(0,0,0,.07)" strokeWidth={1} />
          </pattern>
        ))}
      </defs>
      <g>{bands}</g>
      <line x1={0} y1={ys(50)} x2={W} y2={ys(50)} stroke="#94a3b8" strokeDasharray="2 2" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
      <path d={path} fill="none" stroke="#1e293b" strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
