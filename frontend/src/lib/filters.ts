import type { Theme } from '@/types/themes';
import type { SignalType, ThemeSignal } from '@/types/signals';

/**
 * 主题列表筛选: 按信号类型 + 模糊搜索 (主题名/主 ETF/关联 ETF/tag)。
 */
export function filterThemes(
  themes: Theme[],
  signalsByThemeId: Map<string, ThemeSignal>,
  signalFilter: 'all' | SignalType,
  search: string,
): Theme[] {
  const q = search.trim().toLowerCase();
  return themes.filter((t) => {
    if (signalFilter !== 'all') {
      const ts = signalsByThemeId.get(t.id);
      if (!ts || ts.signal !== signalFilter) return false;
    }
    if (q) {
      const blob = [t.name, t.primary_us, ...t.us_etfs, ...t.tags]
        .join(' ')
        .toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });
}
