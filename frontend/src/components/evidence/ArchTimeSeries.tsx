import {
  Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface TimePoint {
  period: string;
  arch_ratio: number | null;
  arch_count: number | null;
  tested: number | null;
}

interface Props {
  timeSeries: TimePoint[];
}

/** ARCH 显著比例滚动时序 (120 日窗口按月步进): n≈120 功效充足, 给出可比的真实强度时序. */
export const ArchTimeSeries = ({ timeSeries }: Props) => {
  // for 循环 + 独立 const (非 map 返回多行对象字面量), 避免 v8 coverage 对象体盲区
  const data: { period: string; ratio: number }[] = [];
  for (const e of timeSeries) {
    data.push({ period: e.period, ratio: (e.arch_ratio ?? 0) * 100 });
  }
  if (data.length === 0) {
    return <EmptyCard text="暂无 ARCH 时序数据" />;
  }

  return (
    <ChartCard
      title="ARCH 显著比例（逐月·120日滚动）"
      subtitle="波动率聚集强度时序 · hover 看占比"
      helpTitle="ARCH 显著比例时序 · 读法"
      help={
        <>
          <p>柱 = 该月末向前 120 日窗口内 r² Ljung-Box p&lt;0.05 的主题占比（ARCH 显著 = 波动率聚集明显）。</p>
          <p><strong>为何用 120 日滚动</strong>：日历季仅 ~40–66 日、严重欠功率，单季比例被压到 0–14%，绝对值无意义。120 日窗口功效充足，实测范围 3–66%、均值 ~22%，与全样本 87% 可比，反映强度随时间的真实变化。</p>
          <p><strong>解读</strong>：峰值（如 2024-10 ≈66%）= 该窗口多数主题出现波动聚集，常对应行情剧烈阶段；低谷（&lt;10%）= 普遍平静。窗口按月步进、重叠滑动，曲线连续平滑。</p>
          <p>适用：判断当前市场处于波动聚集期还是平静期，辅助波动率/风险建模择时。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="period" tick={{ fontSize: 9 }} interval={5} />
          <YAxis tick={{ fontSize: 10 }} width={40} unit="%" domain={[0, 100]} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'ARCH显著比例']} />
          <ReferenceLine y={50} stroke="#cbd5e1" strokeDasharray="3 3" />
          <Bar dataKey="ratio" fill="#7c3aed" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
