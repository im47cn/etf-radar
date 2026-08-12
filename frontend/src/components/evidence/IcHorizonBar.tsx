import {
  Bar, BarChart, CartesianGrid, ErrorBar, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcHorizon } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface Props {
  byHorizon: IcHorizon[];
}

/** IC vs 持有期: 柱=全样本均值 · ErrorBar=历史min-max · 标签=最近5日实际. */
export const IcHorizonBar = ({ byHorizon }: Props) => {
  const data = byHorizon.map((e) => ({
    horizon: `${e.horizon}d`,
    ic: e.ic ?? 0,
    t_stat: e.t_stat ?? 0,
    ic_min: e.ic_min ?? 0,
    ic_max: e.ic_max ?? 0,
    recent_ic: e.recent_ic ?? 0,
    // ErrorBar dataKey 是相对 ic 值的 [负误差, 正误差], 需把绝对 min/max 转相对
    ic_err_low: (e.ic ?? 0) - (e.ic_min ?? 0),
    ic_err_high: (e.ic_max ?? 0) - (e.ic ?? 0),
  }));
  if (!data.length) {
    return <EmptyCard text="暂无 IC 数据" />;
  }

  return (
    <ChartCard
      title="IC vs 持有期"
      subtitle="柱=均值 · 竖线=历史min-max · 红标=最近5日"
      helpTitle="IC vs 持有期 · 读法"
      help={
        <>
          <p>3 柱 = strength 对未来 1/5/20 日收益的<strong>全样本均值 IC</strong>（5 年）。</p>
          <p><strong>竖线（ErrorBar）</strong> = 全样本逐日 IC 的 min-max（历史波动范围，单日 IC 可大幅偏离均值）。</p>
          <p><strong>红色顶标</strong> = 最近 5 个交易日 IC 均值（当前实际表现，可能偏离长期均值）。</p>
          <p>柱随 horizon 增大 = 慢变量趋势 alpha（月级 &gt; 日级）。</p>
          <p>案例：1d 0.022 → 20d 0.054（单调增，t 均&gt;2）。注：竖线范围宽说明单日 IC 噪声大，均值才稳定可信。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 20, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="horizon" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 10 }} width={44} />
          <Tooltip
            formatter={(value, name) => {
              if (name === 'ic') return [`${Number(value).toFixed(3)} (均值)`, 'IC'];
              return [Number(value).toFixed(3), String(name)];
            }}
          />
          <ReferenceLine y={0} stroke="#94a3b8" />
          <Bar dataKey="ic" fill="#0891b2" radius={[2, 2, 0, 0]}>
            {/* recharts ErrorBar dataKey 运行时支持 [min,max] 数组, 但类型定义未覆盖 -> cast */}
            <ErrorBar dataKey={['ic_err_low', 'ic_err_high'] as unknown as string} width={8} strokeWidth={1.5} stroke="#475569" />
            <LabelList
              dataKey="recent_ic"
              position="top"
              formatter={(v) => `近${Number(v).toFixed(3)}`}
              fontSize={9}
              fill="#dc2626"
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
