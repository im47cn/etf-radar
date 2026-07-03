import useSWR from 'swr';
import { MarketTemperatureSchema, type MarketTemperature } from '@/types/marketTemperature';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.marketTemperature;

const fetcher = async (url: string): Promise<MarketTemperature> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`market_temperature ${res.status}`);
  return MarketTemperatureSchema.parse(await res.json());
};

export interface UseMarketTemperatureResult {
  data: MarketTemperature | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取全市场/行业 MA20 宽度快照. 缺失(旧快照无该文件)时 data=undefined, 由页面降级. */
export function useMarketTemperature(): UseMarketTemperatureResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });
  return { data, error: error as Error | undefined, isLoading };
}
