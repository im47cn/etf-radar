import { useMemo } from 'react';
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard, EmptyCard } from './ChartCard';

interface Props {
  /** theme_id -> r² ACF(0..15) (lag0 恒为 1.0) */
  acf: Record<string, Array<number | null>>;
  /** theme_id -> 中文名 (arch.themes 里取) */
  themeNames: Record<string, string>;
}

const COLORS = ['#dc2626', '#0891b2', '#059669', '#7c3aed'];

/** 代表主题 r² ACF 衰减: 强 ARCH (高位缓降) vs 无 ARCH (迅速回 0). */
export const R2AcfChart = ({ acf, themeNames }: Props) => {
  const themeIds = useMemo(() => Object.keys(acf), [acf]);

  const data = useMemo(() => {
    if (!themeIds.length) return [];
    const lags = acf[themeIds[0]].length;
    return Array.from({ length: lags }, (_, lag) => {
      const row: Record<string, number | string> = { lag };
      for (const id of themeIds) row[id] = acf[id][lag] ?? 0;
      return row;
    });
  }, [acf, themeIds]);

  if (!data.length) return <EmptyCard text="暂无 ACF 数据" />;

  return (
    <ChartCard
      title="代表主题 r² ACF 衰减"
      subtitle="强 ARCH 缓降 vs 无 ARCH 近 0"
      helpTitle="r² ACF 衰减 · 读法"
      help={
        <>
          <p>曲线 = 主题收益率平方的自相关（lag 0-15）。lag0 恒为 1.0（自相关）。</p>
          <p><strong>强 ARCH（半导体/医疗）</strong>：高位缓降 = 波动率聚集明显。</p>
          <p><strong>无 ARCH（白酒/煤炭）</strong>：迅速回 0 = 波动无记忆。</p>
          <p>对比看：波动率建模选缓降主题，均值回归策略选速降主题。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="lag" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value) => Number(value).toFixed(2)} />
          {themeIds.map((id, i) => (
            <Line
              key={id}
              dataKey={id}
              name={themeNames[id] ?? id}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={1.5}
              dot={false}
              type="monotone"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px]">
        {themeIds.map((id, i) => (
          <span key={id} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
            {themeNames[id] ?? id}
          </span>
        ))}
      </div>
    </ChartCard>
  );
};
