import { useContext } from 'react';
import { HoldingsContext, type UseHoldingsResult, type UpsertInput } from '@/providers/holdingsContext';

export type { UseHoldingsResult, UpsertInput };

export function useHoldings(): UseHoldingsResult {
  const v = useContext(HoldingsContext);
  if (!v) throw new Error('useHoldings 必须在 <HoldingsProvider> 内 (见 App.tsx)');
  return v;
}
