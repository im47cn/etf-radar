import { useEffect, useState } from 'react';
import { holdingsEtfUrl } from '@/lib/dataUrls';
import type { EtfHoldingsSnapshot } from '@/types/holdings';

interface UseEtfHoldingsResult {
  data: EtfHoldingsSnapshot[];
  loading: boolean;
  error: Error | null;
}

export function useEtfHoldings(etfCodes: string[]): UseEtfHoldingsResult {
  const isEmpty = etfCodes.length === 0;
  const [data, setData] = useState<EtfHoldingsSnapshot[]>([]);
  const [loading, setLoading] = useState(!isEmpty);
  const [error, setError] = useState<Error | null>(null);

  // 把数组序列化为 join key 避免每次新数组引用导致重复 fetch
  const key = etfCodes.join(',');

  useEffect(() => {
    if (isEmpty) return;
    let cancelled = false;
    // key 变化时同步重置 loading/error 状态，是 fetch-on-key-change 模式的必要部分
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  // isEmpty 时返回 derived 状态，避免在 effect 里同步 setState 触发 cascading renders
  return isEmpty ? { data: [], loading: false, error: null } : { data, loading, error };
}
