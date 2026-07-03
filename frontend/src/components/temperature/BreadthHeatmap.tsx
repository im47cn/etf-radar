import type { BreadthRow } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  dates: string[];
  rows: BreadthRow[];
}

/** 行业(行) × 交易日(列) 站上率颜色矩阵. 行已由后端按 latest 降序. */
export const BreadthHeatmap = ({ dates, rows }: Props) => {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 text-sm font-medium text-gray-700">历史热力图 · 行业 × 交易日</div>
      <table className="border-separate" style={{ borderSpacing: 1 }}>
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-white" />
            {dates.map((d) => (
              <th key={d} className="h-6 w-3 align-bottom">
                <span className="block origin-bottom-left -rotate-90 whitespace-nowrap text-[8px] text-gray-400">
                  {d.slice(5)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td className="sticky left-0 z-10 bg-white pr-2 text-right text-[11px] text-gray-600 whitespace-nowrap">
                {r.name}
              </td>
              {r.series.map((v, i) => (
                <td
                  key={dates[i] ?? i}
                  className="h-4 w-3"
                  style={{ backgroundColor: breadthColor(v) }}
                  title={`${r.name} ${dates[i]}: ${v != null ? v.toFixed(1) + '%' : '无数据'}`}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
