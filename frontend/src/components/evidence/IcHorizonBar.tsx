import {
  Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcHorizon } from '@/types/signalEvidence';

interface Props {
  byHorizon: IcHorizon[];
}

/** IC vs 持有期 (1d/5d/20d). IC 随 horizon 增 = 慢变量趋势 alpha 签名. */
export const IcHorizonBar = ({ byHorizon }: Props) => {
  const data = byHorizon.map((e) => ({
    horizon: `${e.horizon}d`,
    ic: e.ic ?? 0,
    t_stat: e.t_stat ?? 0,
  }));

  if (!data.length) {
    return <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-400">暂无 IC 数据</div>;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">IC vs 持有期</h2>
        <span className="text-[10px] text-gray-400">随 horizon 增 = 慢变量 alpha</span>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="horizon" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value, _name, item) => {
            const t = Number(item?.payload?.t_stat ?? 0);
            return [`${Number(value).toFixed(3)} (t=${t.toFixed(2)})`, 'IC'];
          }} />
          <ReferenceLine y={0} stroke="#94a3b8" />
          <Bar dataKey="ic" fill="#0891b2" radius={[2, 2, 0, 0]}>
            <LabelList dataKey="ic" position="top" formatter={(v) => Number(v).toFixed(3)} fontSize={10} fill="#475569" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
