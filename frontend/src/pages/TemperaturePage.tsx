import { useState } from 'react';
import { useMarketTemperature } from '@/hooks/useMarketTemperature';
import type { BreadthLevel } from '@/types/marketTemperature';
import { BreadthThermometer } from '@/components/temperature/BreadthThermometer';
import { IndustryBreadthRanking } from '@/components/temperature/IndustryBreadthRanking';
import { BreadthHeatmap } from '@/components/temperature/BreadthHeatmap';

const levelBtn = (active: boolean): string =>
  active
    ? 'px-3 py-1 rounded bg-blue-600 text-white text-sm'
    : 'px-3 py-1 rounded text-gray-700 hover:bg-gray-100 text-sm';

export const TemperaturePage = () => {
  const { data, error, isLoading } = useMarketTemperature();
  const [level, setLevel] = useState<BreadthLevel>('l1');

  if (isLoading) return <div className="p-8 text-center text-gray-400">加载中…</div>;
  if (error || !data)
    return <div className="p-8 text-center text-gray-400">暂无市场温度数据</div>;

  const rows = level === 'l1' ? data.industries_l1 : data.industries_l2;

  return (
    <main className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-800">市场温度 · 个股 MA20 站上率</h1>
        <div className="flex gap-1">
          <button className={levelBtn(level === 'l1')} onClick={() => setLevel('l1')}>
            一级行业
          </button>
          <button className={levelBtn(level === 'l2')} onClick={() => setLevel('l2')}>
            二级行业
          </button>
        </div>
      </div>

      <BreadthThermometer market={data.market} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <IndustryBreadthRanking rows={rows} />
        <BreadthHeatmap dates={data.dates} rows={rows} />
      </div>

      <p className="text-xs text-gray-400">
        口径说明：数据源为大盘云图，仅提供行业级 MA20 站上率。「全市场」为各二级行业站上率的
        <span className="font-medium">等权均值</span>
        （数据源无成分股数，无法按个股加权），一级行业为其下二级行业等权聚合。0 值代表无数据、已过滤。
      </p>
    </main>
  );
};
