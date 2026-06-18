import { useMemo } from 'react';
import { useDataContext } from '@/providers/dataContext';
import { useUIState } from '@/providers/uiStateContext';
import { useThemeSignalsMap } from '@/hooks/useData';
import { MappingPanel } from './MappingPanel';
import { PeriodReturns } from './PeriodReturns';
import { StrengthBars } from './StrengthBars';
import { StrengthRing } from './StrengthRing';
import { SignalNote } from './SignalNote';
import { TagPills } from './TagPills';
import { Badge } from '@/components/ui/badge';
import type { SignalType } from '@/types/signals';

const DIM_LABELS = {
  short: '短期',
  mid: '中期',
  long: '长期',
  composite: '综合',
} as const;

const SIGNAL_LABEL: Record<SignalType, string> = {
  resonance: '共振',
  transmission: '传导',
  divergence: '背离',
};

export const ThemeDetail = () => {
  const { themes, signals } = useDataContext();
  const { state } = useUIState();
  const sigMap = useThemeSignalsMap();

  const theme = useMemo(
    () => themes?.themes.find((t) => t.id === state.selectedThemeId),
    [themes, state.selectedThemeId],
  );

  if (!theme) {
    return (
      <div className="bg-white border rounded p-6 text-gray-400 text-sm text-center">
        选择左侧主题查看详情
      </div>
    );
  }
  const ts = sigMap.get(theme.id);
  const pair = signals?.pair_signals.find(
    (p) => p.theme_id === theme.id && p.cn_code === ts?.trigger_cn_etf,
  );

  const dimLabel = DIM_LABELS[state.dimension];

  return (
    <div className="bg-white border rounded p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-lg font-semibold">{theme.name}</div>
          {ts?.description && (
            <div className="text-sm text-gray-500">{ts.description}</div>
          )}
        </div>
        {ts?.signal && <Badge>{SIGNAL_LABEL[ts.signal]}</Badge>}
      </div>

      <MappingPanel theme={theme} confidence={pair?.confidence ?? null} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-3">
          <PeriodReturns returns={theme.returns} />
          <StrengthBars strength={theme.strength} />
        </div>
        <div className="flex items-start justify-center">
          <StrengthRing
            value={theme.strength[state.dimension]}
            label={dimLabel + '强度'}
          />
        </div>
      </div>

      <SignalNote signal={ts?.signal ?? null} />
      <TagPills tags={theme.tags} />
      {theme.note && (
        <div className="bg-gray-50 text-xs text-gray-600 p-2 rounded">
          {theme.note}
        </div>
      )}
    </div>
  );
};
