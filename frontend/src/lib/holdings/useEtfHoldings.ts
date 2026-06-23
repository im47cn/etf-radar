import { useEffect, useState } from 'react';
import { holdingsEtfUrl } from '@/lib/dataUrls';
import type { EtfHoldingsSnapshot } from '@/types/holdings';

interface UseEtfHoldingsResult {
  data: EtfHoldingsSnapshot[];
  loading: boolean;
  error: Error | null;
}

export function useEtfHoldings(etfCodes: string[]): UseEtfHoldingsResult {
  const [data, setData] = useState<EtfHoldingsSnapshot[]>([]);
  const [loading, setLoading] = useState(etfCodes.length > 0);
  const [error, setError] = useState<Error | null>(null);

  // 把数组序列化为 join key 避免每次新数组引用导致重复 fetch
  const key = etfCodes.join(',');

  useEffect(() => {
    let cancelled = false;
    if (etfCodes.length === 0) {
      setData([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    Promise.allSettled(
      etfCodes.map(async code => {
        const res = await fetch(holdingsEtfUrl(code));
        if (!res.ok) throw new Error(`${code}: HTTP ${res.status}`);
        return (await res.json()) as EtfHoldingsSnapshot;
      }),
    ).then(results => {
      if (cancelled) return;
      const ok: EtfHoldingsSnapshot[] = [];
      for (const r of results) {
        if (r.status === 'fulfilled') ok.push(r.value);
      }
      setData(ok);
      setLoading(false);
    });

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, loading, error };
}
