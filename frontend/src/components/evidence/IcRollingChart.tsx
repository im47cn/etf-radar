import { useMemo } from 'react';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcRolling } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from './ChartCard';

interface Props {
  rolling: IcRolling[];
}

/** Strength 月度 IC 时序 (滚动 60 日窗口, forward 20d 收益). */
export const IcRollingChart = ({ rolling }: Props) => {
  const data = useMemo(() => rolling.map((p) => ({ date: p.date, ic: p.ic })), [rolling]);
  const mean = useMemo(() => {
    const vs = data.map((d) => d.ic).filter((v): v is number => v != null);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }, [data]);

  if (!data.length) return <EmptyCard text="暂无 IC 时序数据" />;

  return (
    <ChartCard
      title="Strength 月度 IC（滚动 60 日）"
      subtitle="forward 20d · 红虚线 = 均值"
      helpTitle="IC 滚动时序 · 读法"
      help={
        <>
          <p>曲线每个点 = 过去 60 日横截面 IC 均值（strength 排名 vs 未来 20 日收益排名）。</p>
          <p><strong>持续 &gt; 0</strong>（0 线上方）= 该窗口强度有正预测力；频繁穿越 0 = 不稳定。</p>
          <p><strong>红虚线</strong> = 全期均值（5 年约 +0.054，弱但显著）。</p>
          <p>案例：5 年均值 0.054，但早期（2021-2023）曾转负，alpha 不完全持续；2024 起整体转正。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value) => [Number(value).toFixed(3), 'IC']} />
          <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" />
          {mean != null && (
            <ReferenceLine
              y={mean}
              stroke="#dc2626"
              strokeDasharray="2 2"
              label={{ value: `均值 ${mean.toFixed(3)}`, fontSize: 9, fill: '#dc2626', position: 'insideTopRight' }}
            />
          )}
          <Line dataKey="ic" stroke="#1e293b" strokeWidth={1.5} dot={false} type="monotone" connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
