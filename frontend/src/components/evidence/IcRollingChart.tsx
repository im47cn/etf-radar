import { useMemo } from 'react';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcRolling } from '@/types/signalEvidence';

interface Props {
  rolling: IcRolling[];
}

/** Strength 月度 IC 时序 (滚动 60 日窗口, forward 20d 收益). IC>0 = 强者续强; 均值线看 alpha 持续性. */
export const IcRollingChart = ({ rolling }: Props) => {
  const data = useMemo(
    () => rolling.map((p) => ({ date: p.date, ic: p.ic })),
    [rolling],
  );
  const mean = useMemo(() => {
    const vs = data.map((d) => d.ic).filter((v): v is number => v != null);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }, [data]);

  if (!data.length) {
    return <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">暂无 IC 时序数据</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Strength 月度 IC（滚动 60 日）</h2>
        <span className="text-[10px] text-gray-400">forward 20d · 红虚线 = 均值</span>
      </div>
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
    </div>
  );
};
