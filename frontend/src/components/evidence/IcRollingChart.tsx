import { useMemo, useState } from 'react';
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { IcRolling } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from './ChartCard';

interface Props {
  rolling: IcRolling[];
}

// 5/20/60 三窗口: 5 敏感(噪声大)/20 平衡/60 平滑(趋势). 60 主线加粗.
const SERIES = [
  { key: 'ic_5', label: '5日', color: '#94a3b8', width: 1 },
  { key: 'ic_20', label: '20日', color: '#0891b2', width: 1.25 },
  { key: 'ic_60', label: '60日', color: '#1e293b', width: 2 },
] as const;

/** Strength 月度 IC 多窗口时序 (5/20/60 日滚动, forward 20d 收益). */
export const IcRollingChart = ({ rolling }: Props) => {
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const data = useMemo(
    () => rolling.map((p) => ({ date: p.date, ic_5: p.ic_5, ic_20: p.ic_20, ic_60: p.ic_60 })),
    [rolling],
  );
  const mean60 = useMemo(() => {
    const vs = data.map((d) => d.ic_60).filter((v): v is number => v != null);
    return vs.length ? vs.reduce((a, b) => a + b, 0) / vs.length : null;
  }, [data]);

  if (!data.length) return <EmptyCard text="暂无 IC 时序数据" />;

  const toggle = (k: string) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <ChartCard
      title="Strength 月度 IC（多窗口滚动）"
      subtitle="5/20/60 日 · 红虚线 = 全期均值"
      helpTitle="IC 多窗口时序 · 读法"
      help={
        <>
          <p>曲线 = 过去 N 日横截面 IC 均值（strength 排名 vs 未来 20 日收益排名）。</p>
          <p><strong>三窗口</strong>：5日（敏感、噪声大，看拐点）/ 20日（平衡）/ 60日（平滑、看趋势，主线加粗）。</p>
          <p><strong>持续 &gt; 0</strong> = alpha 稳定；红虚线 = 全期均值（ic_60 长期 alpha 水平，5 年约 0.054，跨三线对照）。</p>
          <p><strong>适用</strong>：判断 alpha 持续性与拐点；<strong>局限</strong>：IC 是排名相关不等于绝对收益，末端 20 日无点（forward 收益未实现）。</p>
          <p>案例：5 年 60 日均值 0.054；2021-2023 曾转负（alpha 不持续），2024 起整体转正。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" minTickGap={40} tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value) => Number(value).toFixed(3)} />
          <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="4 4" />
          {mean60 != null && (
            <ReferenceLine
              y={mean60}
              stroke="#dc2626"
              strokeDasharray="2 2"
              label={{ value: `全期均值 ${mean60.toFixed(3)}`, fontSize: 9, fill: '#dc2626', position: 'insideTopRight' }}
            />
          )}
          {SERIES.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              strokeWidth={s.width}
              dot={false}
              type="monotone"
              connectNulls
              hide={hidden.has(s.key)}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px]">
        {SERIES.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => toggle(s.key)}
            className={`flex cursor-pointer items-center gap-1 transition-opacity ${
              hidden.has(s.key) ? 'opacity-30' : 'opacity-100 hover:text-gray-900'
            }`}
          >
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </button>
        ))}
      </div>
    </ChartCard>
  );
};
