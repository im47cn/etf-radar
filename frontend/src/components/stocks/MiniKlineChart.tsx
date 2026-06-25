import { useStockOhlc } from '@/lib/holdings/useStockOhlc';
import type { StockOhlcBar } from '@/types/stockIndicators';

interface Props {
  code: string;
  width?: number;
  height?: number;
}

const PAD = 4;

export const MiniKlineChart = ({ code, width = 160, height = 80 }: Props) => {
  const { data, loading } = useStockOhlc(code);

  if (loading) {
    return <div className="text-xs text-gray-400 px-1 py-2">加载中...</div>;
  }
  if (!data) {
    return <div className="text-xs text-gray-400 px-1 py-2">无数据</div>;
  }
  if (data.bars.length < 5) {
    return <div className="text-xs text-gray-400 px-1 py-2">数据不足</div>;
  }

  const bars = data.bars.slice(-60);
  const allHighs = bars.map(b => b.h);
  const allLows = bars.map(b => b.l);
  const maxP = Math.max(...allHighs);
  const minP = Math.min(...allLows);
  const range = maxP - minP || 1;
  const innerW = width - 2 * PAD;
  const innerH = height - 2 * PAD;
  const barW = innerW / bars.length;
  const candleW = Math.max(1, barW * 0.7);

  const yFor = (price: number) =>
    PAD + (1 - (price - minP) / range) * innerH;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="bg-white rounded border border-gray-200 shadow-sm"
      aria-label={`${data.name} 60 日 K 线`}
    >
      {bars.map((b: StockOhlcBar, i: number) => {
        const cx = PAD + i * barW + barW / 2;
        const yHigh = yFor(b.h);
        const yLow = yFor(b.l);
        const yOpen = yFor(b.o);
        const yClose = yFor(b.c);
        const up = b.c >= b.o;
        const color = up ? '#e11d48' : '#16a34a';  // 中国市场红涨绿跌
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(1, Math.abs(yClose - yOpen));
        return (
          <g key={`${b.date}-${i}`}>
            <line
              x1={cx} x2={cx} y1={yHigh} y2={yLow}
              stroke={color} strokeWidth={1}
            />
            <rect
              x={cx - candleW / 2}
              y={bodyY}
              width={candleW}
              height={bodyH}
              fill={color}
            />
          </g>
        );
      })}
    </svg>
  );
};
