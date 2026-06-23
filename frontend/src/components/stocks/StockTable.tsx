import type { AggregatedStock } from '@/types/holdings';
import { cn } from '@/lib/utils';

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

export const StockTable = ({ stocks }: Props) => (
  <table className="w-full text-sm border-collapse">
    <thead className="bg-gray-100 text-xs text-gray-600">
      <tr>
        <th className="px-2 py-2 text-center w-12">#</th>
        <th className="px-2 py-2 text-left">代码</th>
        <th className="px-2 py-2 text-left">名称</th>
        <th className="px-2 py-2 text-left">关联 ETF</th>
        <th className="px-2 py-2 text-right">累计权重</th>
        <th className="px-2 py-2 text-right">收盘</th>
        <th className="px-2 py-2 text-right">今日涨跌</th>
      </tr>
    </thead>
    <tbody>
      {stocks.map((s, idx) => {
        const r1d = s.spot?.r_1d ?? null;
        return (
          <tr key={s.code} className="border-b hover:bg-gray-50">
            <td className="px-2 py-2 text-center text-gray-500">{idx + 1}</td>
            <td className="px-2 py-2 font-mono">{s.code}</td>
            <td className="px-2 py-2">{s.name}</td>
            <td className="px-2 py-2">
              <div className="flex flex-wrap gap-1">
                {s.sourceEtfs.map(etf => (
                  <span
                    key={etf}
                    className="px-1.5 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono"
                  >
                    {etf}
                  </span>
                ))}
              </div>
            </td>
            <td className="px-2 py-2 text-right tabular-nums">{formatWeight(s.cumulativeWeight)}</td>
            <td className="px-2 py-2 text-right tabular-nums">{formatPrice(s.spot?.close ?? null)}</td>
            <td className={cn(
              'px-2 py-2 text-right tabular-nums',
              r1d === null ? 'text-gray-400' : r1d >= 0 ? 'text-blue-600' : 'text-red-600',
            )}>
              {formatPct(r1d)}
            </td>
          </tr>
        );
      })}
    </tbody>
  </table>
);
