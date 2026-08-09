import { useMemo } from 'react';
import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { ArchTheme } from '@/types/signalEvidence';

interface Props {
  themes: ArchTheme[];
}

const negLog10P = (p: number | null): number => (p != null && p > 0 ? -Math.log10(p) : 0);
const SIG_LINE = -Math.log10(0.05); // ≈ 1.30

/** 主题 ARCH 显著性排序 (-log10(r² LB p)). 红色=显著(p<0.05); 虚线=显著阈值. */
export const ArchRankingBar = ({ themes }: Props) => {
  const data = useMemo(
    () =>
      themes
        .map((t) => ({ name: t.name ?? t.theme_id, neglogp: negLog10P(t.r2_lb_p), is_arch: t.is_arch === true }))
        .sort((a, b) => b.neglogp - a.neglogp),
    [themes],
  );

  if (!data.length) {
    return <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">暂无 ARCH 数据</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">主题 ARCH 显著性（波动率聚集）</h2>
        <span className="text-[10px] text-gray-400">-log10(p) · 红色 = 显著 · 虚线 = p=0.05</span>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 16)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <XAxis type="number" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 9 }} width={64} />
          <Tooltip formatter={(value) => [Number(value).toFixed(2), '-log10(p)']} />
          <ReferenceLine x={SIG_LINE} stroke="#dc2626" strokeDasharray="4 4" />
          <Bar dataKey="neglogp" radius={[0, 2, 2, 0]}>
            {data.map((d, i) => (
              <Cell key={d.name} fill={d.is_arch ? '#dc2626' : '#cbd5e1'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
