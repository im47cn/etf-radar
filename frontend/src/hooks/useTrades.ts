import { useContext } from 'react';
import { TradesContext, type UseTradesResult } from '@/providers/TradesProvider';

export type { UseTradesResult };

export function useTrades(): UseTradesResult {
  const v = useContext(TradesContext);
  if (!v) throw new Error('useTrades 必须在 <TradesProvider> 内 (见 App.tsx)');
  return v;
}
