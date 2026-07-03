import { useMarketTemperature } from '@/hooks/useMarketTemperature';
import { BreadthThermometer } from '@/components/temperature/BreadthThermometer';
import { IndustryBreadthRanking } from '@/components/temperature/IndustryBreadthRanking';
import { BreadthHeatmap } from '@/components/temperature/BreadthHeatmap';

export const TemperaturePage = () => {
  const { data, error, isLoading } = useMarketTemperature();

  if (isLoading) return <div className="p-8 text-center text-gray-400">加载中…</div>;
  if (error || !data)
    return <div className="p-8 text-center text-gray-400">暂无市场温度数据</div>;

  return (
    <main className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-semibold text-gray-800">市场温度 · 个股 MA20 站上率</h1>

      <BreadthThermometer market={data.market} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <IndustryBreadthRanking l1Rows={data.industries_l1} l2Rows={data.industries_l2} />
        <BreadthHeatmap dates={data.dates} l1Rows={data.industries_l1} l2Rows={data.industries_l2} />
      </div>

      <p className="text-xs text-gray-400">
        口径说明：数据源为大盘云图，仅提供行业级 MA20 站上率。「全市场」为各二级行业站上率的
        <span className="font-medium">等权均值</span>
        （数据源无成分股数，无法按个股加权），一级行业为其下二级行业等权聚合。0 值代表无数据、已过滤。
      </p>
    </main>
  );
};
