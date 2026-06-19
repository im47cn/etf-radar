import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useUIState } from '@/providers/uiStateContext';
import { useThemeSignalsMap } from '@/hooks/useData';
import { filterThemes } from '@/lib/filters';
import { ThemeRow } from './ThemeRow';

const DIM_LABELS = {
  short: '短期',
  mid: '中期',
  long: '长期',
  composite: '综合',
} as const;

export const ThemeList = () => {
  const { themes } = useDataContext();
  const { state, dispatch } = useUIState();
  const sigMap = useThemeSignalsMap();

  const sorted = useMemo(() => {
    if (!themes) return [];
    return [...themes.themes].sort(
      (a, b) => b.strength[state.dimension] - a.strength[state.dimension],
    );
  }, [themes, state.dimension]);

  const visible = useMemo(
    () => (state.onlyCnOnly ? sorted.filter((t) => t.primary_us === null) : sorted),
    [sorted, state.onlyCnOnly],
  );

  const filtered = useMemo(
    () => filterThemes(visible, sigMap, state.signalFilter, state.searchQuery),
    [visible, sigMap, state.signalFilter, state.searchQuery],
  );

  return (
    <div className="bg-white border rounded">
      <div className="p-3 border-b">
        <div className="font-medium">美股主题强弱</div>
        <div className="text-xs text-gray-500">
          按{DIM_LABELS[state.dimension]}强弱排序 · {filtered.length}/{sorted.length} 个主题
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-600">
            <tr>
              <th className="px-2 py-2 text-center">#</th>
              <th className="px-2 py-2 text-left">主题</th>
              <th className="px-2 py-2 text-left">主ETF</th>
              <th className="px-2 py-2 text-left">强度</th>
              <th className="px-2 py-2 text-right">近1日</th>
              <th className="px-2 py-2 text-right">近1周</th>
              <th className="px-2 py-2 text-center">信号</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <ThemeRow
                key={t.id}
                index={i}
                theme={t}
                signal={sigMap.get(t.id)}
                dimension={state.dimension}
                selected={state.selectedThemeId === t.id}
                onClick={() => dispatch({ type: 'SELECT_THEME', id: t.id })}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
