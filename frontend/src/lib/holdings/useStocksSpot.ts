import { useEffect, useState } from 'react';
import { LATEST_URLS } from '@/lib/dataUrls';
import type { StockSpot } from '@/types/holdings';
import { StocksSpotFileSchema } from '@/types/holdings';

interface UseStocksSpotResult {
  spots: Record<string, StockSpot> | null;
  loading: boolean;
}

export function useStocksSpot(): UseStocksSpotResult {
  const [spots, setSpots] = useState<Record<string, StockSpot> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(LATEST_URLS.stocksSpot)
      .then(async res => (res.ok ? StocksSpotFileSchema.parse(await res.json()) : null))
      .then(file => {
        if (cancelled) return;
        setSpots(file?.stocks ?? null);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setSpots(null);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return { spots, loading };
}
