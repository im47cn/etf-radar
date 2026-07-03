import { Fragment, useMemo, useState } from 'react';
import type { BreadthRow } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  dates: string[];
  l1Rows: BreadthRow[];
  l2Rows: BreadthRow[];
}

/**
 * 行业(行) × 交易日(列) 站上率颜色矩阵, 按一级行业折叠.
 * 默认只显示 26 个一级行业(聚合); 点开某一级展开其下二级行业.
 */
export const BreadthHeatmap = ({ dates, l1Rows, l2Rows }: Props) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // l1 名 -> 其二级子行业(保持后端已排序顺序)
  const childrenByL1 = useMemo(() => {
    const m = new Map<string, BreadthRow[]>();
    for (const r of l2Rows) {
      const key = r.l1 ?? '其他';
      (m.get(key) ?? m.set(key, []).get(key)!).push(r);
    }
    return m;
  }, [l2Rows]);

  const toggle = (name: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const cells = (r: BreadthRow) =>
    r.series.map((v, i) => (
      <td
        key={dates[i] ?? i}
        className="h-4 w-3"
        style={{ backgroundColor: breadthColor(v) }}
        title={`${r.name} ${dates[i]}: ${v != null ? v.toFixed(1) + '%' : '无数据'}`}
      />
    ));

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">历史热力图 · 行业 × 交易日</span>
        <span className="text-[11px] text-gray-400">点一级行业展开二级</span>
      </div>
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
          {l1Rows.map((r) => {
            const isOpen = expanded.has(r.name);
            const kids = childrenByL1.get(r.name) ?? [];
            return (
              <Fragment key={r.name}>
                <tr>
                  <td className="sticky left-0 z-10 bg-white pr-2 whitespace-nowrap text-right">
                    <button
                      className="text-[11px] font-medium text-gray-700 hover:text-blue-600"
                      onClick={() => toggle(r.name)}
                      aria-expanded={isOpen}
                    >
                      <span className="inline-block w-3 text-gray-400">{kids.length ? (isOpen ? '▾' : '▸') : ''}</span>
                      {r.name}
                    </button>
                  </td>
                  {cells(r)}
                </tr>
                {isOpen &&
                  kids.map((k) => (
                    <tr key={`${r.name}/${k.name}`}>
                      <td className="sticky left-0 z-10 bg-gray-50 py-px pr-2 pl-4 whitespace-nowrap text-right text-[10px] text-gray-500">
                        {k.name}
                      </td>
                      {cells(k)}
                    </tr>
                  ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
