import { useCallback, useState } from 'react';

export interface TrailRange {
  startOffset: number;
  endOffset: number;
}

export interface UseTrailRangeReturn {
  range: TrailRange;
  setRange: (range: TrailRange) => void;
  reset: () => void;
}

export const MAX_TRAIL_DAYS = 30;
export const DEFAULT_TRAIL_DAYS = 10;

const DEFAULT_RANGE: TrailRange = { startOffset: -DEFAULT_TRAIL_DAYS, endOffset: 0 };
const MIN_START = -MAX_TRAIL_DAYS;
const MAX_END = 0;

export function useTrailRange(): UseTrailRangeReturn {
  const [range, setRangeState] = useState<TrailRange>(DEFAULT_RANGE);

  const setRange = useCallback((next: TrailRange) => {
    const clampedStart = Math.max(MIN_START, next.startOffset);
    const clampedEnd = Math.min(MAX_END, next.endOffset);
    if (clampedStart >= clampedEnd) return;
    setRangeState({ startOffset: clampedStart, endOffset: clampedEnd });
  }, []);

  const reset = useCallback(() => setRangeState(DEFAULT_RANGE), []);

  return { range, setRange, reset };
}
