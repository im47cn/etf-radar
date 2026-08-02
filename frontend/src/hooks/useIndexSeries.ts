import useSWR from 'swr';
import { IndexSeriesSchema, type IndexSeries } from '@/types/indexSeries';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.indexSeries;

const fetcher = async (url: string): Promise<IndexSeries> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`index_series ${res.status}`);
  return IndexSeriesSchema.parse(await res.json());
};

export interface UseIndexSeriesResult {
  data: IndexSeries | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取 A 股主要指数收盘价序列 (供温度页对比图叠加). 缺失时 data=undefined, 由页面降级. */
export function useIndexSeries(): UseIndexSeriesResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });
  return { data, error: error as Error | undefined, isLoading };
}
