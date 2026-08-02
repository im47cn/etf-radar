import { useState, useMemo } from 'react';
import { useMarketTemperature } from '@/hooks/useMarketTemperature';
import { useIndexSeries } from '@/hooks/useIndexSeries';
import { PERIOD_KEYS, PERIOD_LABELS, type PeriodKey } from '@/types/marketTemperature';
import { BreadthThermometer } from '@/components/temperature/BreadthThermometer';
import { IndexCompareChart } from '@/components/temperature/IndexCompareChart';
import { IndustryBreadthRanking } from '@/components/temperature/IndustryBreadthRanking';
import { BreadthHeatmap } from '@/components/temperature/BreadthHeatmap';
import { BreadthLegend } from '@/components/temperature/BreadthLegend';
import { Skeleton } from '@/components/ui/skeleton';

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
        <h1 className="text-lg font-semibold text-gray-800">个股 MA 站上率</h1>
        <div className="flex gap-1">
          {PERIOD_KEYS.map((k) => {
            const disabled = !data.available.includes(k);
            return (
              <button
                key={k}
                className={periodBtn(activePeriod === k, disabled)}
                disabled={disabled}
                title={disabled ? '历史数据不足，暂无该周期' : undefined}
                onClick={() => setPeriod(k)}
              >
                {PERIOD_LABELS[k]}
              </button>
            );
          })}
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
