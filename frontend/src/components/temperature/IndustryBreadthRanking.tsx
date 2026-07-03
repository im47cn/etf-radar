import { useMemo, useState } from 'react';
import type { BreadthRow } from '@/types/marketTemperature';
import { breadthColor } from '@/lib/breadthColor';

interface Props {
  l1Rows: BreadthRow[];
  l2Rows: BreadthRow[];
}

const byLatestDesc = (a: BreadthRow, b: BreadthRow): number => {
  if (a.latest == null) return 1;
  if (b.latest == null) return -1;
  return b.latest - a.latest;
};

interface BarProps {
  row: BreadthRow;
  indent?: boolean;
  caret?: string;
  onClick?: () => void;
  /** 一级行业: 其下二级行业站上率的 min/max 区间, 叠加"须"式标记直观展示分布. */
  range?: { min: number; max: number };
}

const Bar = ({ row, indent, caret, onClick, range }: BarProps) => (
  <div className="flex items-center gap-2 text-xs">
    <button
      className={`flex ${indent ? 'w-24 pl-5' : 'w-24'} shrink-0 items-center gap-0.5 truncate text-left ${onClick ? 'hover:text-blue-600' : 'cursor-default'} ${indent ? 'text-gray-500' : 'text-gray-700'}`}
      onClick={onClick}
      disabled={!onClick}
      title={row.name}
    >
      {caret !== undefined && <span className="w-3 shrink-0 text-gray-400">{caret}</span>}
      <span className="truncate">{row.name}</span>
    </button>
    <div
      className="relative h-4 flex-1 rounded bg-gray-100"
      title={range ? `子行业区间 ${range.min.toFixed(1)}–${range.max.toFixed(1)}%` : undefined}
    >
      <div
        className="h-4 rounded"
        style={{ width: `${row.latest ?? 0}%`, backgroundColor: breadthColor(row.latest) }}
      />
      {range && (
        <>
          {/* 连接线: min→max */}
          <div
            className="absolute top-1/2 h-px -translate-y-1/2 bg-gray-500/70"
            style={{ left: `${range.min}%`, width: `${Math.max(0, range.max - range.min)}%` }}
          />
          {/* 端点须: min / max */}
          <div className="absolute inset-y-1 w-px bg-gray-600" style={{ left: `${range.min}%` }} />
          <div className="absolute inset-y-1 w-px bg-gray-600" style={{ left: `${range.max}%` }} />
        </>
      )}
    </div>
    <span className="w-12 shrink-0 text-right tabular-nums text-gray-700">
      {row.latest != null ? `${row.latest.toFixed(1)}%` : '—'}
    </span>
  </div>
);

/** 一级行业下二级行业 latest 的 min/max (过滤 null); 无有效子行业返回 null. */
const childRange = (kids: BreadthRow[]): { min: number; max: number } | null => {
  const vals = kids.map((k) => k.latest).filter((v): v is number => v != null);
  if (vals.length < 2) return null; // 单个子行业无区间意义
  return { min: Math.min(...vals), max: Math.max(...vals) };
};

/** 行业当日站上率条形排行, 门类折叠树 + 一键展开全部. */
export const IndustryBreadthRanking = ({ l1Rows, l2Rows }: Props) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const childrenByL1 = useMemo(() => {
    const m = new Map<string, BreadthRow[]>();
    for (const r of l2Rows) {
      const key = r.l1 ?? '其他';
      (m.get(key) ?? m.set(key, []).get(key)!).push(r);
    }
    for (const rows of m.values()) rows.sort(byLatestDesc);
    return m;
  }, [l2Rows]);

  const sortedL1 = useMemo(() => [...l1Rows].sort(byLatestDesc), [l1Rows]);
  const allExpanded = expanded.size > 0 && sortedL1.every((r) => expanded.has(r.name));

  const toggle = (name: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const toggleAll = () =>
    setExpanded(allExpanded ? new Set() : new Set(sortedL1.map((r) => r.name)));

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">行业排行 · 当日站上率</span>
        <button
          className="rounded px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
          onClick={toggleAll}
        >
          {allExpanded ? '收起全部' : '展开全部'}
        </button>
      </div>
      <div className="flex flex-col gap-1">
        {sortedL1.map((r) => {
          const isOpen = expanded.has(r.name);
          const kids = childrenByL1.get(r.name) ?? [];
          return (
            <div key={r.name} className="flex flex-col gap-1">
              <Bar
                row={r}
                caret={kids.length ? (isOpen ? '▾' : '▸') : ''}
                onClick={kids.length ? () => toggle(r.name) : undefined}
                range={childRange(kids) ?? undefined}
              />
              {isOpen && kids.map((k) => <Bar key={`${r.name}/${k.name}`} row={k} indent caret="" />)}
            </div>
          );
        })}
      </div>
    </div>
  );
};
