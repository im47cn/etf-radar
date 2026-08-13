import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface TimePoint {
  period: string;
  arch_ratio: number | null;
  arch_count: number | null;
  tested: number | null;
  is_partial?: boolean | null;
}

interface Props {
  timeSeries: TimePoint[];
}

/** ARCH 显著比例逐季时序: 波动率聚集随时间变化. 最新未完整季(is_partial)样本不足仍保留. */
export const ArchTimeSeries = ({ timeSeries }: Props) => {
  const data = timeSeries.map((e) => ({
    period: e.period,
    ratio: (e.arch_ratio ?? 0) * 100,
    label: `${e.arch_count ?? 0}/${e.tested ?? 0}${e.is_partial ? '*' : ''}`,
    partial: e.is_partial ?? false,
  }));
  if (!data.length) {
    return <EmptyCard text="暂无 ARCH 时序数据" />;
  }

  return (
    <ChartCard
      title="ARCH 显著比例（逐季）"
      subtitle="波动率聚集随时间变化 · 标签=显著/总主题"
      helpTitle="ARCH 显著比例时序 · 读法"
      help={
        <>
          <p>柱 = 该季 r² Ljung-Box p&lt;0.05 的主题占比（ARCH 显著 = 波动率聚集明显）。</p>
          <p><strong>逐季 vs 全样本</strong>：单季比例（实测 0–14%）远低于全样本 87%——单季仅 ~40–66 交易日、严重欠功率，约两成季检不出（0%）；全样本（1212 日）累积才达 87%。两者不矛盾。</p>
          <p><strong>解读</strong>：仅剧烈波动季（如 2022-Q1、2024-Q3 ≈14%）能检出聚集；其余季贴近 0%。注意 0% 不代表无聚集，而是样本不足以检出——勿读作「平静期」。</p>
          <p><strong>* 最新季</strong>：浅色柱 = 当前未完整季（&lt;40 日），样本严重不足，仅作参考、勿据以下结论；因它代表「当下」故保留显示。</p>
          <p>适用：判断当前市场是否处于波动聚集期；季级欠功率，看趋势而非单点。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} unit="%" domain={[0, 100]} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'ARCH显著比例']} />
          <ReferenceLine y={50} stroke="#cbd5e1" strokeDasharray="3 3" />
          <Bar dataKey="ratio" radius={[2, 2, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.period} fill={d.partial ? '#c4b5fd' : '#7c3aed'} />
            ))}
            <LabelList dataKey="label" position="top" fontSize={9} fill="#6b7280" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
