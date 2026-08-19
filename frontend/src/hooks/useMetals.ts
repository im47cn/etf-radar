import useSWR from 'swr';
import { MetalsSchema, type Metals } from '@/types/metals';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.metals;

const fetcher = async (url: string): Promise<Metals> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`metals ${res.status}`);
  return MetalsSchema.parse(await res.json());
};

export interface UseMetalsResult {
  data: Metals | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取贵金属宏观指标快照 (金银比/实际利率代理/DXY/金矿杠杆比). 缺失时 data=undefined, 由页面降级. */
export function useMetals(): UseMetalsResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });
  return { data, error: error as Error | undefined, isLoading };
}
