import useSWR from 'swr';
import { normalizeMarketTemperature, type NormalizedTemperature } from '@/types/marketTemperature';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.marketTemperature;

const fetcher = async (url: string): Promise<NormalizedTemperature> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`market_temperature ${res.status}`);
  return normalizeMarketTemperature(await res.json());
};

export interface UseMarketTemperatureResult {
  data: NormalizedTemperature | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取全市场/行业多周期宽度快照(归一化 1.0/2.0). 缺失时 data=undefined, 由页面降级. */
export function useMarketTemperature(): UseMarketTemperatureResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });
  return { data, error: error as Error | undefined, isLoading };
}
