import {
  Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { GridFitnessTheme } from '@/types/signalEvidence';
import { ChartCard, EmptyCard } from '@/components/ChartCard';

interface Props {
  themes: GridFitnessTheme[];
}

const VERDICT_COLOR: Record<string, string> = {
  suitable: '#059669',   // 绿: 适合网格
  marginal: '#d97706',   // 琥珀: 中性/谨慎
  unsuitable: '#9ca3af', // 灰: 不适合
};

export interface GridRow {
  name: string; score: number; vol: number; hurst: number; verdict: string;
  ret60: number | null; ret120: number | null; trendRegime: string | null;
  volForecast: number | null;  // GARCH 前瞻 60 日年化波动
}

/** 主题 → 网格排名行 (grid_score 降序 + verdict 缺省兜底). 模块级纯函数便于直接测试. */
export function buildGridData(themes: GridFitnessTheme[]): GridRow[] {
  const data: GridRow[] = [];
  for (const t of themes) {
    const verdict = t.verdict ?? 'marginal';
    const base = t.name ?? t.theme_id;
    // 趋势护栏降级主题加 ⚠ 前缀, 一眼可见 (tooltip 展示近期涨跌详情)
    const name = t.trend_regime ? `⚠ ${base}` : base;
    const score = t.grid_score ?? 0;
    const vol = t.ann_vol ?? 0;
    const hurst = t.hurst ?? 0.5;
    data.push({
      name, score, vol, hurst, verdict,
      ret60: t.ret_60d ?? null, ret120: t.ret_120d ?? null,
      trendRegime: t.trend_regime ?? null,
      volForecast: t.vol_forecast_ann ?? null,
    });
  }
  data.sort((a, b) => b.score - a.score);
  return data;
}

const TREND_WARN: Record<string, string> = {
  down: '近期单边下跌：网格接飞刀有套牢风险，已强制降级',
  up: '近期单边上涨：网格会踏空，已强制降级',
};

const fmtPct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`);

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: GridRow }>;
}

/** 排名条 hover 详情: 复合分 + 子维度 + 近期涨跌与趋势护栏警示. */
export const GridTooltip = ({ active, payload }: TooltipProps) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-md border border-gray-200 bg-white/95 px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-gray-800">{d.name}</p>
      <p className="text-gray-600">复合分 {d.score.toFixed(3)} · 年化波动 {(d.vol * 100).toFixed(1)}% · Hurst {d.hurst.toFixed(3)}</p>
      <p className="text-gray-500">前瞻波动(GARCH) {fmtPct(d.volForecast)}</p>
      <p className="text-gray-500">近60日 {fmtPct(d.ret60)} · 近120日 {fmtPct(d.ret120)}</p>
      {d.trendRegime && (
        <p className="mt-1 text-red-600">⚠ {TREND_WARN[d.trendRegime] ?? '近期强趋势，已强制降级'}</p>
      )}
    </div>
  );
};

export interface TickProps { x: number | string; y: number | string; payload: { value?: string } }
// recharts vertical interval=0 默认 tick 渲染有 bug, 自定义确保行业名全显
export const renderNameTick = ({ x, y, payload }: TickProps) => (
  <text x={Number(x) - 4} y={Number(y)} dy={3} textAnchor="end" fontSize={9} fill="#6b7280">
    {payload.value ?? ''}
  </text>
);

/** 主题网格适配度排名: 高波动 + 均值回归 + ARCH 持续 → 适合网格交易的程度. */
export const GridFitnessRanking = ({ themes }: Props) => {
  const data = buildGridData(themes);
  if (!data.length) return <EmptyCard text="暂无网格适配度数据" />;

  return (
    <ChartCard
      title="主题网格适配度排名"
      subtitle="复合分 = 波动率(0.40) + 均值回归(0.35) + ARCH(0.25) · hover 看子分"
      helpTitle="网格适配度 · 读法"
      help={
        <>
          <p>横条 = 主题网格适配度复合分（0–1，越高越适合网格）。<strong>绿 = 适合</strong>（≥0.65），琥珀 = 中性（0.40–0.65），灰 = 不适合（&lt;0.40）。</p>
          <p><strong>前瞻波动率</strong>：GARCH(1,1) 预测的未来 60 日年化波动（5 年样本验证：QLIKE 优于无条件基线 15%，p&lt;0.01）。高于历史年化波动=预期更动荡，反之类推；用于仓位/风控参考，不预测方向。</p>
          <p><strong>三维度</strong>（跨主题百分位加权）：① <strong>波动率</strong>（年化 σ，利润空间，0.40）② <strong>均值回归</strong>（Hurst H&lt;0.5 震荡/网格友好，H&gt;0.5 趋势/危险，0.35）③ <strong>ARCH 持续</strong>（波动不衰减，0.25）。</p>
          <p><strong>⚠ 边界</strong>：Hurst&gt;0.55（强趋势）或近 60/120 日累计涨跌超 ±10%/±15%（单边 regime）无论分数强制降为中性——单边下跌套牢、单边上涨踏空。名字带 ⚠ 即触发趋势护栏，hover 看详情。这是统计信号<strong>非保证盈利</strong>，需结合当前价位区间、ETF 流动性与趋势实判。</p>
          <p>用法：绿色主题具备更适配网格的波动特征，可作选标的参考；避免灰/趋势主题。<strong>5 年回测</strong>：该分数对网格相对静态持有的超额收益仅有微弱排序力（头尾差约 0.26%/年化），适合 = 特征适配，<strong>不等于多赚</strong>；需配合网格参数（间距/层数）与风控。</p>
        </>
      }
    >
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 16)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={renderNameTick} width={80} interval={0} />
          <Tooltip content={<GridTooltip />} />
          <ReferenceLine x={0.65} stroke="#059669" strokeDasharray="4 4" />
          <ReferenceLine x={0.4} stroke="#d97706" strokeDasharray="4 4" />
          <Bar dataKey="score" radius={[0, 2, 2, 0]}>
            {data.map((d) => (
              <Cell key={d.name} fill={VERDICT_COLOR[d.verdict] ?? '#9ca3af'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
};
