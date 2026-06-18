import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import type { ThemeSignal } from '@/types/signals';

/**
 * 把 signals.theme_signals 转成 Map<theme_id, ThemeSignal>, 便于 ThemeList 行级 O(1) 查找。
 */
export const useThemeSignalsMap = (): Map<string, ThemeSignal> => {
  const { signals } = useDataContext();
  return useMemo(() => {
    const m = new Map<string, ThemeSignal>();
    signals?.theme_signals.forEach((ts) => m.set(ts.theme_id, ts));
    return m;
  }, [signals]);
};
