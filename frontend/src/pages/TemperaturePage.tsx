import { useState, useMemo } from 'react';
import { useMarketTemperature } from '@/hooks/useMarketTemperature';
import { PERIOD_KEYS, PERIOD_LABELS, type PeriodKey } from '@/types/marketTemperature';
import { BreadthThermometer } from '@/components/temperature/BreadthThermometer';
import { IndustryBreadthRanking } from '@/components/temperature/IndustryBreadthRanking';
import { BreadthHeatmap } from '@/components/temperature/BreadthHeatmap';
import { BreadthLegend } from '@/components/temperature/BreadthLegend';

const periodBtn = (active: boolean, disabled: boolean): string => {
  if (disabled) return 'px-3 py-1 rounded text-gray-300 cursor-not-allowed text-sm';
  return active
    ? 'px-3 py-1 rounded bg-blue-600 text-white text-sm'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100 text-sm';
};

export const TemperaturePage = () => {
  const { data, error, isLoading } = useMarketTemperature();
  const [period, setPeriod] = useState<PeriodKey>('ma20');

  // 选中周期不可用时回退到首个可用周期
  const activePeriod = useMemo<PeriodKey | undefined>(() => {
    if (!data) return undefined;
    if (data.available.includes(period)) return period;
    return data.available[0];
  }, [data, period]);

  if (isLoading) return <div className="p-8 text-center text-gray-400">加载中…</div>;
  if (error || !data || !activePeriod)
    return <div className="p-8 text-center text-gray-400">暂无市场温度数据</div>;

  const pd = data.periods[activePeriod]!;

  return (
    <main className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-800">市场温度 · 个股 MA 站上率</h1>
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
      <BreadthLegend />

      <BreadthThermometer market={pd.market} periodLabel={PERIOD_LABELS[activePeriod]} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <IndustryBreadthRanking l1Rows={pd.industries_l1} l2Rows={pd.industries_l2} />
        <BreadthHeatmap dates={data.dates} l1Rows={pd.industries_l1} l2Rows={pd.industries_l2} />
      </div>

      <p className="text-xs text-gray-400">
        口径说明：全市场/行业为
        <span className="font-medium">个股</span>
        价格站上 {PERIOD_LABELS[activePeriod]} 的真实占比（站上数 ÷ 有效样本数）。停牌、上市不足周期长度的新股不计入分母；无行业归属个股计入全市场、不计入行业。行业分类采用巨潮体系。
      </p>
    </main>
  );
};
