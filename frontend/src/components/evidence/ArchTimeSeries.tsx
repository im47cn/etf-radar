import {
  Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard, EmptyCard } from './ChartCard';

interface TimePoint {
  period: string;
  arch_ratio: number | null;
  arch_count: number | null;
  tested: number | null;
}

interface Props {
  timeSeries: TimePoint[];
}

/** ARCH 显著比例逐年时序: 波动率聚集随时间变化. 单年因样本短检出率低, 全样本累积才高. */
export const ArchTimeSeries = ({ timeSeries }: Props) => {
  const data = timeSeries.map((e) => ({
    period: e.period,
    ratio: (e.arch_ratio ?? 0) * 100,
    label: `${e.arch_count ?? 0}/${e.tested ?? 0}`,
  }));
  if (!data.length) {
    return <EmptyCard text="暂无 ARCH 时序数据" />;
  }

  return (
    <ChartCard
      title="ARCH 显著比例（逐年）"
      subtitle="波动率聚集随时间变化 · 标签=显著/总主题"
      helpTitle="ARCH 显著比例时序 · 读法"
      help={
        <>
          <p>柱 = 该年 r² Ljung-Box p&lt;0.05 的主题占比（ARCH 显著 = 波动率聚集明显）。</p>
          <p><strong>逐年 vs 全样本</strong>：单年比例（13–55%）远低于全样本 87%——单年样本短（~240 日）功率不足，全样本（1212 日）累积才达 87%。两者不矛盾。</p>
          <p><strong>解读</strong>：峰值年（如 2024 ≈55%）= 该年波动率聚集最强；低谷年（2025–26 ≈13%）= 平静期。</p>
          <p>适用：判断当前市场处于波动聚集期还是平静期，辅助波动率/风险建模择时。</p>
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
          <Bar dataKey="ratio" fill="#7c3aed" radius={[2, 2, 0, 0]}>
            <LabelList dataKey="label" position="top" fontSize={9} fill="#6b7280" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
