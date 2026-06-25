import { useEffect, useState } from 'react';
import { stockOhlcUrl } from '@/lib/dataUrls';
import type { StockOhlc } from '@/types/stockIndicators';

interface UseStockOhlcResult {
  data: StockOhlc | null;
  loading: boolean;
  error: Error | null;
}

// 模块级缓存：同一个 code 跨组件重渲染只 fetch 一次
const cache = new Map<string, StockOhlc>();

export function useStockOhlc(code: string | null): UseStockOhlcResult {
  const [data, setData] = useState<StockOhlc | null>(null);
  const [loading, setLoading] = useState(code !== null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (code === null) return;

    const cached = cache.get(code);
    if (cached) {
      // 命中缓存时同步重置 data/loading，是 fetch-on-key-change 模式的必要部分
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setData(cached);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    // code 变化时同步重置 loading/error 状态，是 fetch-on-key-change 模式的必要部分
    setLoading(true);
    setError(null);

    fetch(stockOhlcUrl(code))
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) return null;
          throw new Error(`HTTP ${res.status}`);
        }
        return res.json() as Promise<StockOhlc>;
      })
      .then(payload => {
        if (cancelled) return;
        if (payload) cache.set(code, payload);
        setData(payload);
        setLoading(false);
      })
      .catch(e => {
        if (cancelled) return;
        setError(e as Error);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [code]);

  // code===null 时返回 derived 状态，避免在 effect 里同步 setState 触发 cascading renders
  return code === null ? { data: null, loading: false, error: null } : { data, loading, error };
}
