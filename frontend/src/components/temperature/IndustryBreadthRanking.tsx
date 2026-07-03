import { useMemo, useState } from 'react';
import type { BreadthRow, BreadthLevel } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  l1Rows: BreadthRow[];
  l2Rows: BreadthRow[];
}

const tabBtn = (active: boolean): string =>
  active
    ? 'px-2 py-0.5 rounded bg-blue-600 text-white text-xs'
    : 'px-2 py-0.5 rounded text-gray-600 hover:bg-gray-100 text-xs';

/** 行业当日站上率条形排行, 自带一级/二级切换. null 值排末尾. */
export const IndustryBreadthRanking = ({ l1Rows, l2Rows }: Props) => {
  const [level, setLevel] = useState<BreadthLevel>('l1');
  const rows = level === 'l1' ? l1Rows : l2Rows;

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
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">行业排行 · 当日站上率</span>
        <div className="flex gap-1">
          <button className={tabBtn(level === 'l1')} onClick={() => setLevel('l1')}>
            一级
          </button>
          <button className={tabBtn(level === 'l2')} onClick={() => setLevel('l2')}>
            二级
          </button>
        </div>
      </div>
      <div className="flex flex-col gap-1">
        {sorted.map((r) => (
          <div key={r.name} className="flex items-center gap-2 text-xs">
            <span className="w-16 shrink-0 truncate text-gray-600" title={r.name}>
              {r.name}
            </span>
            <div className="relative h-4 flex-1 rounded bg-gray-100">
              <div
                className="h-4 rounded"
                style={{ width: `${r.latest ?? 0}%`, backgroundColor: breadthColor(r.latest) }}
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
