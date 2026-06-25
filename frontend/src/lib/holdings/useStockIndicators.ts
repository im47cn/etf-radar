import { useEffect, useState } from 'react';
import { STOCKS_URLS } from '@/lib/dataUrls';
import type { HoldingsIndicatorsFile, StockIndicators } from '@/types/stockIndicators';

interface UseStockIndicatorsResult {
  data: Map<string, StockIndicators>;
  loading: boolean;
  error: Error | null;
}

const EMPTY: Map<string, StockIndicators> = new Map();

export function useStockIndicators(): UseStockIndicatorsResult {
  const [data, setData] = useState<Map<string, StockIndicators>>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(STOCKS_URLS.holdingsIndicators)
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) {
            // backfill 未跑过 / 数据缺失，静默返回空 Map
            return null;
          }
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json() as Promise<HoldingsIndicatorsFile>;
      })
      .then(payload => {
        if (cancelled) return;
        if (!payload) {
          setData(EMPTY);
        } else {
          setData(new Map(Object.entries(payload.stocks)));
        }
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e as Error);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { data, loading, error };
}
