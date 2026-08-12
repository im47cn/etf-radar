import { ChartCard, EmptyCard } from '@/components/ChartCard';
import type { MarketBreadth } from '@/lib/marketBreadth';

/** 小数收益 → 带符号百分比, null 显示占位符。A 股语境: 正为涨。 */
function fmtSignedPct(v: number | null): string {
  if (v === null) return '—';
  const sign = v >= 0 ? '+' : '-';
  return `${sign}${(Math.abs(v) * 100).toFixed(2)}%`;
}

export interface MarketThermometerProps {
  breadth: MarketBreadth;
}

/**
 * 市场温度计: 一条"涨跌家数"广度条 + 中位收益。
 * 配色遵循 A 股习惯 (红涨绿跌), 与象限图的"轮动象限配色"语义正交。
 * 补象限图 (RRG 相对图) 对全市场普涨/普跌的盲区。
 */
export const MarketThermometer = ({ breadth }: MarketThermometerProps) => {
  const { total, up, down, flat, breadthPct, medianR1d } = breadth;

  if (total === 0) {
    return <EmptyCard text="市场温度数据不足" />;
  }

  const upPct = (up / total) * 100;
  const downPct = (down / total) * 100;
  const flatPct = (flat / total) * 100;
  const medianClass =
    medianR1d === null || medianR1d === 0
      ? 'text-gray-500'
      : medianR1d > 0
        ? 'text-red-600'
        : 'text-green-600';

  return (
    <ChartCard
      title="市场温度计"
      subtitle="全市场涨跌家数广度 · 红涨绿跌"
      helpTitle="市场温度计 · 读法"
      help={
        <>
          <p>涨/跌/平家数 + 上涨占比 + 中位收益；底部三色广度条按家数占比（红涨绿跌灰平）。</p>
          <p>与象限图正交：象限图看主题相对强弱，温度计看全市场普涨/普跌。</p>
          <p>CN 模式用 41 只主题 ETF r_1d；US 模式用主题美股锚点 r_1d。</p>
        </>
      }
    >
      <div className="flex items-center justify-between mb-1.5 text-xs">
        <div className="flex items-center gap-2 sm:gap-3 tabular-nums">
          <span className="text-red-600 font-medium">涨 {up}</span>
          <span className="text-green-600 font-medium">跌 {down}</span>
          <span className="text-gray-500">平 {flat}</span>
        </div>
        <div className="flex items-center gap-2 sm:gap-3 tabular-nums">
          <span className="text-gray-600">上涨占比 {Math.round(breadthPct)}%</span>
          <span className="text-gray-600">
            中位 <span className={`font-semibold ${medianClass}`}>{fmtSignedPct(medianR1d)}</span>
          </span>
        </div>
      </div>
      {/* 广度条: 红=涨 绿=跌 灰=平, 宽度按家数占比 */}
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-gray-100" aria-hidden="true">
        <div className="bg-red-500" style={{ width: `${upPct}%` }} />
        <div className="bg-green-500" style={{ width: `${downPct}%` }} />
        <div className="bg-gray-300" style={{ width: `${flatPct}%` }} />
      </div>
    </ChartCard>
  );
};
