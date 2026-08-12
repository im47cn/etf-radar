import { useMemo } from 'react';
import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { ArchTheme } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface Props {
  themes: ArchTheme[];
}

const negLog10P = (p: number | null): number => (p != null && p > 0 ? -Math.log10(p) : 0);
const SIG_LINE = -Math.log10(0.05); // ≈ 1.30

// 自定义 YAxis tick: recharts vertical interval=0 默认 tick 渲染有 bug, 自定义确保行业名全显
interface TickProps { x: number | string; y: number | string; payload: { value?: string } }
const renderNameTick = ({ x, y, payload }: TickProps) => (
  <text x={Number(x) - 4} y={Number(y)} dy={3} textAnchor="end" fontSize={9} fill="#6b7280">
    {payload.value ?? ''}
  </text>
);

/** 主题 ARCH 显著性排序 (-log10(r² LB p)). 红色 = 显著(p<0.05); 虚线 = 显著阈值. */
export const ArchRankingBar = ({ themes }: Props) => {
  const data = useMemo(
    () =>
      themes
        .map((t) => ({ name: t.name ?? t.theme_id, neglogp: negLog10P(t.r2_lb_p), is_arch: t.is_arch === true }))
        .sort((a, b) => b.neglogp - a.neglogp),
    [themes],
  );

  if (!data.length) return <EmptyCard text="暂无 ARCH 数据" />;

  return (
    <ChartCard
      title="主题 ARCH 显著性（波动率聚集）"
      subtitle="-log10(p) · 红色 = 显著 · 虚线 = p=0.05"
      helpTitle="主题 ARCH 排序 · 读法"
      help={
        <>
          <p>横条 = 主题收益率平方 r² 的 -log10(Ljung-Box p)。<strong>红 = 显著</strong>（p&lt;0.05，有波动率聚集），灰 = 不显著；越高越显著。</p>
          <p>显著 = 高波动日后倾向延续高波动，适合波动率/风险建模；不显著 = 波动无记忆。</p>
          <p>案例：5 年下 <strong>87%（26/30）主题显著</strong>，集中高贝塔（半导体/医疗/黄金）；白酒/煤炭/银行无 ARCH。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 16)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <XAxis type="number" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={renderNameTick} width={80} interval={0} />
          <Tooltip formatter={(value) => [Number(value).toFixed(2), '-log10(p)']} />
          <ReferenceLine x={SIG_LINE} stroke="#dc2626" strokeDasharray="4 4" />
          <Bar dataKey="neglogp" radius={[0, 2, 2, 0]}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.is_arch ? '#dc2626' : '#cbd5e1'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
