import useSWR from 'swr';
import { TradingSchema, type Trading } from '@/types/trading';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.trading;

const fetcher = async (url: string): Promise<Trading> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`trading ${res.status}`);
  return TradingSchema.parse(await res.json());
};

export interface UseTradingResult {
  data: Trading | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取 SEPA 交易信号快照 (环境档位/候选池). 缺失时 data=undefined, 由页面降级. */
export function useTrading(): UseTradingResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    // 静态 JSON 产物 (404=未产出) 重试无意义, 立即降级显示占位
    shouldRetryOnError: false,
  });
  return { data, error: error as Error | undefined, isLoading };
}
