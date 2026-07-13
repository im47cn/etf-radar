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
      <button onClick={() => navigate(-1)} className="text-blue-600 text-sm mb-3">← 返回</button>
      <header className="mb-4">
        <h2 className="text-lg font-semibold">{theme.name} · 主题成分股</h2>
        <p className="text-xs text-gray-500">
          关联 ETF: {etfCodes.join(' · ')}
          {holdings[0]?.disclosure_date && (
            <span className="ml-2">披露日 {holdings[0].disclosure_date}</span>
          )}
        </p>
      </header>
      {loading ? (
        <div className="space-y-2 py-4" aria-busy="true" aria-label="加载中">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : aggregated.length === 0 ? (
        <EmptyState message="本主题暂无持仓披露，将在下个季度更新" />
      ) : (
        <>
          <ThemeStructureSummary stocks={aggregated} />
          <StockTable stocks={aggregated} />
        </>
      )}
    </div>
  );
};
