import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useUIState } from '@/providers/uiStateContext';
import { useThemeSignalsMap } from '@/hooks/useData';
import { usePortfolioScores } from '@/hooks/usePortfolioScores';
import { filterThemes } from '@/lib/filters';
import { pickStrength, themeMatchesView } from '@/lib/marketView';
import { ThemeRow } from './ThemeRow';

const DIM_LABELS = {
  short: '短期',
  mid: '中期',
  long: '长期',
  composite: '综合',
} as const;

const VIEW_TITLES = {
  us:       '美股主题强弱',
  'cn-all': 'A 股主题强弱',
} as const;

export const ThemeList = () => {
  const { themes } = useDataContext();
  const { state, dispatch } = useUIState();
  const sigMap = useThemeSignalsMap();
  const { ownedThemeIds } = usePortfolioScores();
  const { dimension, marketView } = state;

  // 1) 过滤到当前视角的主题集
  const inView = useMemo(() => {
    if (!themes) return [];
    return themes.themes.filter((t) => themeMatchesView(t, marketView));
  }, [themes, marketView]);

  // 2) 按 mode-aware strength[dim] 排序
  // invariant: themeMatchesView 已确保 pickStrength(t, mv) != null;
  // ?? -1 仅作 strength[dim] 字段缺失的兜底防御.
  const sorted = useMemo(() => {
    return [...inView].sort((a, b) => {
      const sa = pickStrength(a, marketView)?.[dimension] ?? -1;
      const sb = pickStrength(b, marketView)?.[dimension] ?? -1;
      return sb - sa;
    });
  }, [inView, marketView, dimension]);

  // 3) signal + search 过滤
  const filtered = useMemo(
    () => filterThemes(sorted, sigMap, state.signalFilter, state.searchQuery),
    [sorted, sigMap, state.signalFilter, state.searchQuery],
  );

  return (
    <div className="bg-white border rounded">
      <div className="p-3 border-b">
        <div className="font-medium">{VIEW_TITLES[marketView]}</div>
        <div className="text-xs text-gray-500">
          按{DIM_LABELS[dimension]}强弱排序 · {filtered.length}/{inView.length} 个主题
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
                dimension={dimension}
                marketView={marketView}
                selected={state.selectedThemeId === t.id}
                onClick={() => dispatch({ type: 'SELECT_THEME', id: t.id })}
                owned={ownedThemeIds.has(t.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
