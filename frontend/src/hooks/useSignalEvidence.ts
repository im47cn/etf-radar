import useSWR from 'swr';
import { SignalEvidenceSchema, type SignalEvidence } from '@/types/signalEvidence';
import { LATEST_URLS } from '@/lib/dataUrls';

const URL = LATEST_URLS.signalEvidence;

const fetcher = async (url: string): Promise<SignalEvidence> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`signal_evidence ${res.status}`);
  return SignalEvidenceSchema.parse(await res.json());
};

export interface UseSignalEvidenceResult {
  data: SignalEvidence | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/** 拉取 strength IC + 主题 ARCH 统计证据 (月度预计算). 缺失时 data=undefined, 页面降级. */
export function useSignalEvidence(): UseSignalEvidenceResult {
  const { data, error, isLoading } = useSWR(URL, fetcher, {
    revalidateOnFocus: false,
    errorRetryInterval: 5000,
  });
  return { data, error: error as Error | undefined, isLoading };
}
