import { useSignalEvidence } from '@/hooks/useSignalEvidence';
import { GridFitnessRanking } from '@/components/evidence/GridFitnessRanking';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';
import { Skeleton } from '@/components/ui/skeleton';
import { FeatureGate } from '@/components/gate/FeatureGate';

const GRID_HELP: HelpSection[] = [
  {
    title: '网格交易与适配度',
    children: [
      <p key="what">
        <strong>网格交易</strong>：在价格区间内分档挂买卖，震荡市高抛低吸获利。盈利依赖：① 波动幅度（利润空间）
        ② 区间震荡（非单边趋势） ③ 波动持续。
      </p>,
      <p key="score">
        <strong>网格适配度复合分</strong> = 波动率(0.40) + 均值回归Hurst(0.35) + ARCH持续(0.25)，
        跨主题百分位加权。绿=suitable(≥0.65)，琥珀=marginal(0.40–0.65)，灰=unsuitable。
        名字带 <strong>⚠</strong> = 近期单边趋势（近60日涨跌超 ±10% 或近120日超 ±15%），hover 看近期涨跌详情。
      </p>,
    ],
  },
  {
    title: '⚠ 风险与边界',
    children: [
      <p key="risk">
        <strong>趋势是网格天敌</strong>：Hurst&gt;0.55 或近 60/120 日累计涨跌超 ±10%/±15%（单边 regime）
        无论分数强制降为中性——单边上涨踏空、单边下跌套牢。高波动分可能来自暴跌本身，护栏兜底。
        统计信号<strong>非保证盈利</strong>，需结合当前价位区间、ETF 流动性、趋势实判。
      </p>,
      <p key="notdir">
        适配度与<strong>方向择时无关</strong>（实测 ARCH vs 指数涨跌 r≈0）。选方向看证据页 IC；网格只关心"震荡幅度与持续性"。
      </p>,
    ],
  },
];

const GridContent = () => {
  const { data, error, isLoading } = useSignalEvidence();

  if (isLoading)
    return (
      <div className="flex flex-col gap-4 p-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-20" />
        <Skeleton className="h-64" />
      </div>
    );
  if (error || !data) return <div className="p-8 text-center text-gray-400">暂无网格适配度数据</div>;

  const g = data.grid_fitness;
  const themes = g?.themes ?? [];
  // 市场级趋势 regime 提示: 过半主题触发趋势护栏时, 网格机会稀缺是市场状态而非数据异常
  const trendCount = themes.filter((t) => t.trend_regime).length;
  const isTrendRegime = themes.length > 0 && trendCount / themes.length >= 0.5;
  const summary = g
    ? ` · tested ${g.summary.tested} / suitable ${g.summary.suitable_count} / median ${g.summary.median_score}`
    : '';
  return (
    <main className="flex flex-col gap-4 animate-crossfade">
      <div className="flex items-start justify-between gap-2 animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <div>
          <h1 className="text-lg font-semibold text-gray-800">网格选标</h1>
          <p className="mt-0.5 text-xs text-gray-500">
            主题网格适配度 · 高波动+均值回归主题排序（特征适配参考，非收益预测）{summary}
          </p>
        </div>
        <PageHelp title="网格选标" sections={GRID_HELP} />
      </div>

      {isTrendRegime && (
        <p
          className="animate-fade-rise rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700"
          style={{ animationDelay: '60ms' }}
          role="status"
        >
          ⚠ 当前 {trendCount}/{themes.length} 个主题处于单边趋势（近60日涨跌超 ±10% 或近120日超 ±15%），
          已强制降级为中性——趋势市网格机会稀缺，谨慎开新网格。
        </p>
      )}

      <div className="animate-fade-rise" style={{ animationDelay: '120ms' }}>
        <GridFitnessRanking themes={g?.themes ?? []} />
      </div>

      <p className="animate-fade-rise text-xs text-gray-400" style={{ animationDelay: '180ms' }}>
        口径：波动率 = 年化 σ（std×√252）；Hurst = R/S 重标极差（H&lt;0.5 均值回归，H&gt;0.5 趋势）；
        ARCH = r² Ljung-Box。复合分跨主题百分位加权，月度预计算。
      </p>
    </main>
  );
};

export const GridPage = () => (
  <FeatureGate copy="grid" required="member">
    <div className="max-w-6xl mx-auto p-4">
      <GridContent />
    </div>
  </FeatureGate>
);
