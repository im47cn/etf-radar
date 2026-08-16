import { useState, useMemo } from 'react';
import { useMarketTemperature } from '@/hooks/useMarketTemperature';
import { useIndexSeries } from '@/hooks/useIndexSeries';
import { PERIOD_KEYS, PERIOD_LABELS, PERIOD_LABELS_SHORT, type PeriodKey } from '@/types/marketTemperature';
import { BreadthThermometer } from '@/components/temperature/BreadthThermometer';
import { IndexCompareChart } from '@/components/temperature/IndexCompareChart';
import { IndustryBreadthRanking } from '@/components/temperature/IndustryBreadthRanking';
import { BreadthHeatmap } from '@/components/temperature/BreadthHeatmap';
import { BreadthLegend } from '@/components/temperature/BreadthLegend';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

/** 个股 MA 站上率帮助文案: 宽度口径 + 读法 + 常见误读. */
const TEMPERATURE_HELP: HelpSection[] = [
  {
    title: '理论基础',
    children: [
      <p key="def">
        <strong>个股 MA 站上率</strong> = 价格站上均线的个股数 ÷ 有效样本数。停牌、上市不足该周期长度的新股
        <strong>不计入分母</strong>。这是市场<strong>宽度</strong>指标（参与面），不是指数点位。
      </p>,
      <p key="periods">
        四个周期：MA5（短期情绪）/ MA20（月线）/ MA60（季线）/ MA120（半年线）。周期越长，站上率变化越缓慢、
        趋势性越强。
      </p>,
    ],
  },
  {
    title: '使用方法',
    children: [
      <p key="r1">① 顶部切周期；MA5 视图仅展示最近 60 个交易日（短周期看长无意义）。</p>,
      <p key="r2">② <strong>温度计</strong>：全市场站上率的当前值与历史分位。</p>,
      <p key="r3">③ <strong>指数对比</strong>：站上率 vs 主要指数走势，看宽度与点位的背离。</p>,
      <p key="r4">④ <strong>行业宽度排名 + 热力图</strong>：一/二级行业站上率横向对比与时间序列。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>站上率是宽度、不是点位预测</strong>：站上率 80% 不代表指数见顶，只代表参与面广。</p>,
      <p key="m1b"><strong>温度档位（冰点/过热等）无择时预测力</strong>：5 年回测显示宽度状态与指数此后的涨跌基本无关（相关系数 ≈ −0.02）；「过热/冰点」只是对当前参与面的描述，<strong>不是买卖信号</strong>。</p>,
      <p key="m2"><strong>行业分类采用巨潮体系</strong>；无行业归属的个股计入全市场、不计入行业。</p>,
    ],
  },
];

/** MA5 视图仅展示最近 N 个交易日. */
const MA5_DAYS = 60;

const periodBtn = (active: boolean, disabled: boolean): string => {
  if (disabled) return 'px-3 py-1 rounded text-gray-300 cursor-not-allowed text-sm';
  return active
    ? 'px-3 py-1 rounded bg-blue-600 text-white text-sm transition-all duration-150'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100 text-sm transition-all duration-150 active:scale-95';
};

export const TemperaturePage = () => {
  const { data, error, isLoading } = useMarketTemperature();
  const { data: indexSeries } = useIndexSeries();
  const [period, setPeriod] = useState<PeriodKey>('ma5');

  // 选中周期不可用时回退到首个可用周期
  const activePeriod = useMemo<PeriodKey | undefined>(() => {
    if (!data) return undefined;
    if (data.available.includes(period)) return period;
    return data.available[0];
  }, [data, period]);

  const clipStart = useMemo(() => {
    if (!data || activePeriod !== 'ma5') return 0;
    return Math.max(0, data.dates.length - MA5_DAYS);
  }, [data, activePeriod]);

  if (isLoading)
    return (
      <div className="flex flex-col gap-4 p-4" aria-busy="true" aria-label="加载中">
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
        <Skeleton className="h-24" />
      </div>
    );
  if (error || !data || !activePeriod)
    return <div className="p-8 text-center text-gray-400">暂无市场温度数据</div>;

  const pd = data.periods[activePeriod]!;
  const dates = data.dates.slice(clipStart);
  const market = pd.market.slice(clipStart);
  const l1Rows =
    clipStart > 0 ? pd.industries_l1.map((r) => ({ ...r, series: r.series.slice(clipStart) })) : pd.industries_l1;
  const l2Rows =
    clipStart > 0 ? pd.industries_l2.map((r) => ({ ...r, series: r.series.slice(clipStart) })) : pd.industries_l2;
  // 指数序列同样按 clipStart 裁剪, 保持与 market/dates 等长对齐
  const indicesRows =
    clipStart > 0 && indexSeries
      ? indexSeries.indices.map((r) => ({ ...r, series: r.series.slice(clipStart) }))
      : indexSeries?.indices ?? [];

  return (
    <main className="flex flex-col gap-4 p-4 animate-crossfade">
      <div className="flex items-center justify-between animate-fade-rise" style={{ animationDelay: '0ms' }}>
        <h1 className="text-lg font-semibold text-gray-800">个股站上率</h1>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {PERIOD_KEYS.map((k) => {
              const disabled = !data.available.includes(k);
              return (
                <button
                  key={k}
                  className={periodBtn(activePeriod === k, disabled)}
                  disabled={disabled}
                  title={disabled ? '历史数据不足，暂无该周期' : PERIOD_LABELS[k]}
                  onClick={() => setPeriod(k)}
                >
                  {PERIOD_LABELS_SHORT[k]}
                </button>
              );
            })}
          </div>
          <PageHelp title="个股 MA 站上率" sections={TEMPERATURE_HELP} />
        </div>
      </div>

      {/* 页面级单一共享图例: 三图之上、两栏之前 */}
      <div className="animate-fade-rise" style={{ animationDelay: '60ms' }}>
        <BreadthLegend />
      </div>

      <div className="animate-fade-rise" style={{ animationDelay: '120ms' }}>
        <BreadthThermometer market={market} />
      </div>

      <div className="animate-fade-rise" style={{ animationDelay: '150ms' }}>
        <IndexCompareChart market={market} indices={indicesRows} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 animate-fade-rise" style={{ animationDelay: '180ms' }}>
        <IndustryBreadthRanking l1Rows={l1Rows} l2Rows={l2Rows} />
        <BreadthHeatmap
          dates={dates}
          l1Rows={l1Rows}
          l2Rows={l2Rows}
          maxCols={activePeriod === 'ma5' ? MA5_DAYS : 45}
        />
      </div>

      <p className="text-xs text-gray-400 animate-fade-rise" style={{ animationDelay: '240ms' }}>
        口径说明：全市场/行业为
        <span className="font-medium">个股</span>
        价格站上 {PERIOD_LABELS[activePeriod]} 的真实占比（站上数 ÷ 有效样本数）。停牌、上市不足周期长度的新股不计入分母；无行业归属个股计入全市场、不计入行业。行业分类采用巨潮体系。
      </p>
    </main>
  );
};
