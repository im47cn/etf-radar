import { useMemo, useState } from 'react';
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard, EmptyCard } from './ChartCard';

interface Props {
  /** theme_id -> r² ACF(0..15) (全主题, lag0 恒为 1.0) */
  acf: Record<string, Array<number | null>>;
  /** theme_id -> 中文名 */
  themeNames: Record<string, string>;
}

const COLORS = ['#dc2626', '#0891b2', '#059669', '#7c3aed', '#d97706', '#db2777', '#65a30d', '#0ea5e9'];

/** 代表主题 r² ACF 衰减: 全主题, 默认显强 ARCH 2 + 无 ARCH 2, toggle 其余. */
export const R2AcfChart = ({ acf, themeNames }: Props) => {
  const themeIds = useMemo(() => Object.keys(acf), [acf]);

  // 按 lag1 acf 降序 (强 ARCH 在前), 默认显前 2 + 后 2, 其余隐藏
  const sortedIds = useMemo(
    () => [...themeIds].sort((a, b) => (acf[b][1] ?? 0) - (acf[a][1] ?? 0)),
    [acf, themeIds],
  );
  const [hidden, setHidden] = useState<Set<string>>(() =>
    new Set(sortedIds.length > 4 ? sortedIds.slice(2, -2) : []),
  );

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

  const toggle = (id: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const visibleIds = sortedIds.filter((id) => !hidden.has(id));

  return (
    <ChartCard
      title="主题 r² ACF 衰减（全行业）"
      subtitle="默认显强/弱代表 · 点图例切换全部"
      helpTitle="r² ACF 衰减 · 读法"
      help={
        <>
          <p>曲线 = 主题收益率平方的自相关（lag 0-15）。lag0 恒为 1.0。</p>
          <p><strong>默认显示</strong>：lag1 最高的 2 个（强 ARCH）+ 最低的 2 个（无 ARCH），其余隐藏可点图例展开。</p>
          <p><strong>缓降</strong> = 波动率聚集（ARCH 明显，高波动延续）；<strong>速降回 0</strong> = 波动无记忆。</p>
          <p>适用：波动率建模选缓降主题，均值回归策略选速降主题。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="lag" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value) => Number(value).toFixed(2)} />
          {visibleIds.map((id, i) => (
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
      <div className="mt-2 flex flex-wrap justify-center gap-x-2 gap-y-1 text-[10px]">
        {sortedIds.map((id) => {
          const isHidden = hidden.has(id);
          const colorIdx = visibleIds.indexOf(id);
          const color = colorIdx >= 0 ? COLORS[colorIdx % COLORS.length] : '#cbd5e1';
          return (
            <button
              key={id}
              type="button"
              onClick={() => toggle(id)}
              className={`flex cursor-pointer items-center gap-1 transition-opacity ${
                isHidden ? 'opacity-30' : 'opacity-100 hover:text-gray-900'
              }`}
            >
              <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
              {themeNames[id] ?? id}
            </button>
          );
        })}
      </div>
    </ChartCard>
  );
};
