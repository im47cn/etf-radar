import { useMemo } from 'react';
import type { BreadthRow } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  rows: BreadthRow[];
}

/** 行业当日站上率条形排行 (已由后端按 latest 降序). null 值排末尾. */
export const IndustryBreadthRanking = ({ rows }: Props) => {
  const sorted = useMemo(
    () =>
      [...rows].sort((a, b) => {
        if (a.latest == null) return 1;
        if (b.latest == null) return -1;
        return b.latest - a.latest;
      }),
    [rows],
  );

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 text-sm font-medium text-gray-700">行业排行 · 当日站上率</div>
      <div className="flex flex-col gap-1">
        {sorted.map((r) => (
          <div key={r.name} className="flex items-center gap-2 text-xs">
            <span className="w-16 shrink-0 truncate text-gray-600" title={r.name}>
              {r.name}
            </span>
            <div className="relative h-4 flex-1 rounded bg-gray-100">
              <div
                className="h-4 rounded"
                style={{
                  width: `${r.latest ?? 0}%`,
                  backgroundColor: breadthColor(r.latest),
                }}
              />
            </div>
            <span className="w-12 shrink-0 text-right tabular-nums text-gray-700">
              {r.latest != null ? `${r.latest.toFixed(1)}%` : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
