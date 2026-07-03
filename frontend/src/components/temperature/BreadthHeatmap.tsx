import { Fragment, useMemo, useState } from 'react';
import type { BreadthRow } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  dates: string[];
  l1Rows: BreadthRow[];
  l2Rows: BreadthRow[];
  /** 只显示最近 N 个交易日, 避免长周期(如 150 日)矩阵过宽 + 前导无数据留白. */
  maxCols?: number;
}

/**
 * 行业(行) × 交易日(列) 站上率颜色矩阵, 按一级行业折叠.
 * 默认只显示一级行业(聚合); 点开某一级展开其下二级行业.
 * 只画最近 maxCols 列 (长周期 SMA 前导无值, 且列太多过宽).
 */
export const BreadthHeatmap = ({ dates, l1Rows, l2Rows, maxCols = 45 }: Props) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // 最近 maxCols 列: 裁 dates 与每行 series 的尾部
  const start = Math.max(0, dates.length - maxCols);
  const viewDates = useMemo(() => dates.slice(start), [dates, start]);
  const clip = (r: BreadthRow): BreadthRow => ({ ...r, series: r.series.slice(start) });

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

  // 传入已裁剪的行, 用 viewDates 对齐
  const cells = (r: BreadthRow) =>
    clip(r).series.map((v, i) => (
      <td
        key={viewDates[i] ?? i}
        className="h-2.5 w-2.5 min-w-[0.625rem] p-0"
        style={{ backgroundColor: breadthColor(v) }}
        title={`${r.name} ${viewDates[i]}: ${v != null ? v.toFixed(1) + '%' : '无数据'}`}
      />
    ));

  // 名称列固定宽 + 右边框, 防止数据列滑到其下被遮挡
  const nameCol = 'sticky left-0 z-10 w-28 min-w-[7rem] max-w-[7rem] border-r border-gray-200';

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">历史热力图 · 行业 × 交易日</span>
        <span className="text-[11px] text-gray-400">点一级行业展开二级</span>
      </div>
      <table className="border-separate" style={{ borderSpacing: 1 }}>
        <thead>
          <tr>
            <th className={`${nameCol} z-20 bg-white`} />
            {viewDates.map((d) => (
              <th key={d} className="h-8 w-2.5 min-w-[0.625rem] p-0 align-bottom">
                <div className="mx-auto text-[8px] leading-none text-gray-400 [writing-mode:vertical-rl]">
                  {d.slice(5)}
                </div>
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
                  <td className={`${nameCol} bg-white pr-2`}>
                    <button
                      className="flex w-full items-center gap-0.5 text-[10px] leading-none font-medium text-gray-700 hover:text-blue-600"
                      onClick={() => toggle(r.name)}
                      aria-expanded={isOpen}
                    >
                      <span className="w-2.5 shrink-0 text-gray-400">{kids.length ? (isOpen ? '▾' : '▸') : ''}</span>
                      <span className="truncate">{r.name}</span>
                    </button>
                  </td>
                  {cells(r)}
                </tr>
                {isOpen &&
                  kids.map((k) => (
                    <tr key={`${r.name}/${k.name}`}>
                      <td className={`${nameCol} bg-gray-50 pl-5 pr-2`}>
                        <span className="block truncate text-[9px] leading-none text-gray-500">{k.name}</span>
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
