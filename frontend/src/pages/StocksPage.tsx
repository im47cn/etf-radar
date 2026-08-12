import { useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDataContext } from '@/providers/dataContext';
import { useEtfHoldings } from '@/lib/holdings/useEtfHoldings';
import { useStocksSpot } from '@/lib/holdings/useStocksSpot';
import { useStockIndicators } from '@/lib/holdings/useStockIndicators';
import { aggregateHoldings } from '@/lib/holdings/aggregator';
import { StockTable } from '@/components/stocks/StockTable';
import { ThemeStructureSummary } from '@/components/stocks/ThemeStructureSummary';
import { EmptyState } from '@/components/stocks/EmptyState';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHelp, type HelpSection } from '@/components/help/PageHelp';

/** 主题成分股帮助文案: 持仓聚合口径 + 读法 + 常见误读. */
const STOCKS_HELP: HelpSection[] = [
  {
    title: '理论基础',
    children: [
      <p key="src">
        本页聚合该主题的 A 股锚点 ETF（primary_cn）最新持仓披露，叠加个股 spot（现价/涨跌）与指标
        （L2 行业、动量标签）。用于看主题<strong>内部结构</strong>——谁在拉动、集中度如何。
      </p>,
    ],
  },
  {
    title: '使用方法',
    children: [
      <p key="r1">① <strong>结构摘要</strong>：头部 N 大权重股集中度，判断是龙头驱动还是普涨。</p>,
      <p key="r2">② <strong>成分表</strong>：权重、现价、涨跌、L2 行业、动量标签。点列头排序。</p>,
      <p key="r3">③ 顶部显示关联 ETF 与<strong>披露日</strong>——持仓数据的基准日期。</p>,
    ],
  },
  {
    title: '常见误读',
    children: [
      <p key="m1"><strong>持仓按季度披露、有延迟</strong>：ETF 持仓每季度公告一次，期间可能已调仓。</p>,
      <p key="m2"><strong>仅 A 股 ETF</strong>：本期只抓 A 股锚点 ETF 持仓，美股个股数据将在后续阶段上线。</p>,
    ],
  },
];

export const StocksPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { themes: themesFile } = useDataContext();
  const theme = themesFile?.themes?.find(t => t.id === id);

  // 仅取 A 股 ETF（primary_cn）；本期不抓美股 ETF 持仓
  const etfCodes = useMemo(() => {
    if (!theme) return [];
    return theme.primary_cn ? [theme.primary_cn] : [];
  }, [theme]);

  const { data: holdings, loading: holdingsLoading } = useEtfHoldings(etfCodes);
  const { spots, loading: spotsLoading } = useStocksSpot();
  const { data: indicators } = useStockIndicators();

  const aggregated = useMemo(
    () => aggregateHoldings(holdings, spots ?? {}, indicators),
    [holdings, spots, indicators],
  );

  if (!theme) {
    return (
      <div className="max-w-5xl mx-auto p-4">
        <button onClick={() => navigate(-1)} className="text-blue-600 text-sm mb-3">← 返回</button>
        <EmptyState message="未找到该主题" />
      </div>
    );
  }

  if (!theme.primary_cn) {
    return (
      <div className="max-w-5xl mx-auto p-4">
        <button onClick={() => navigate(-1)} className="text-blue-600 text-sm mb-3">← 返回</button>
        <h2 className="text-lg font-semibold mb-3">{theme.name}</h2>
        <EmptyState message="本主题美股个股数据将在 Phase 2 上线" />
      </div>
    );
  }

  const loading = holdingsLoading || spotsLoading;

  return (
    <div className="max-w-5xl mx-auto p-4">
      <button onClick={() => navigate(-1)} className="text-blue-600 text-sm mb-3 animate-fade-in">← 返回</button>
      <header className="mb-4 animate-fade-rise flex items-start justify-between gap-2" style={{ animationDelay: '60ms' }}>
        <div>
          <h2 className="text-lg font-semibold">{theme.name} · 主题成分股</h2>
          <p className="text-xs text-gray-500">
            关联 ETF: {etfCodes.join(' · ')}
            {holdings[0]?.disclosure_date && (
              <span className="ml-2">披露日 {holdings[0].disclosure_date}</span>
            )}
          </p>
        </div>
        <PageHelp title="主题成分股" sections={STOCKS_HELP} />
      </header>
      {loading ? (
        <div className="space-y-2 py-4 animate-fade-rise" aria-busy="true" aria-label="加载中" style={{ animationDelay: '120ms' }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : aggregated.length === 0 ? (
        <EmptyState message="本主题暂无持仓披露，将在下个季度更新" />
      ) : (
        <>
          <div className="animate-fade-rise" style={{ animationDelay: '120ms' }}>
            <ThemeStructureSummary stocks={aggregated} />
          </div>
          <div className="animate-fade-rise" style={{ animationDelay: '180ms' }}>
            <StockTable stocks={aggregated} />
          </div>
        </>
      )}
    </div>
  );
};
