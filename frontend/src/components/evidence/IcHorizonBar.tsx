import {
  Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcHorizon } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from './ChartCard';

interface Props {
  byHorizon: IcHorizon[];
}

/** IC vs 持有期 (1d/5d/20d). IC 随 horizon 增 = 慢变量趋势 alpha 签名. */
export const IcHorizonBar = ({ byHorizon }: Props) => {
  const data = byHorizon.map((e) => ({ horizon: `${e.horizon}d`, ic: e.ic ?? 0, t_stat: e.t_stat ?? 0 }));
  if (!data.length) return <EmptyCard text="暂无 IC 数据" />;

  return (
    <ChartCard
      title="IC vs 持有期"
      subtitle="随 horizon 增 = 慢变量 alpha"
      helpTitle="IC vs 持有期 · 读法"
      help={
        <>
          <p>3 柱 = strength 对未来 1 / 5 / 20 日收益的预测力（全样本横截面 IC 均值）。</p>
          <p><strong>柱随 horizon 增大</strong> = 慢变量趋势 alpha（月级预测力 &gt; 日级）。</p>
          <p>案例：1d 0.022 → 5d 0.029 → 20d 0.054，单调增；t 均 &gt; 2（显著）。注：短样本（半年）曾高估到 0.14，5 年真实约其 1/3。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="horizon" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip
            formatter={(value, _n, item) => {
              const t = Number(item?.payload?.t_stat ?? 0);
              return [`${Number(value).toFixed(3)} (t=${t.toFixed(2)})`, 'IC'];
            }}
          />
          <ReferenceLine y={0} stroke="#94a3b8" />
          <Bar dataKey="ic" fill="#0891b2" radius={[2, 2, 0, 0]}>
            <LabelList dataKey="ic" position="top" formatter={(v) => Number(v).toFixed(3)} fontSize={10} fill="#475569" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
