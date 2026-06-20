import { useMemo, useRef } from 'react';
import { useTrailRange } from '@/hooks/useTrailRange';
import { useFocusedTheme } from '@/hooks/useFocusedTheme';
import { useUIState } from '@/providers/uiStateContext';
import { marketViewToRotationMode } from '@/lib/marketView';
import { TrailRangeSlider } from './TrailRangeSlider';
import { RotationScatterWithTrails } from './RotationScatterWithTrails';
import { FocusedThemePanel } from './FocusedThemePanel';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  snapshots: SnapshotFrame[];
}

export const RotationTrailsOverlay = ({ themes, snapshots }: Props) => {
  const { range, setRange } = useTrailRange();
  const { state } = useUIState();
  const mode = marketViewToRotationMode(state.marketView);

  const validThemeIds = useMemo(() => new Set(themes.map(t => t.id)), [themes]);
  const containerRef = useRef<HTMLDivElement>(null);
  const { focusedId, toggle, setFocused } = useFocusedTheme({
    validThemeIds,
    containerRef,
  });

  const trailFrames = useMemo(() => {
    if (snapshots.length === 0) return [];
    const lastIdx = snapshots.length - 1;
    const startIdx = Math.max(0, lastIdx + range.startOffset);
    const endIdx = Math.max(startIdx, lastIdx + range.endOffset);
    const base = snapshots.slice(startIdx, endIdx + 1);
    // 当用户的 trail 终点对齐"今天"(endOffset === 0)时, 追加一帧从 themes 实时数据派生的
    // T-0 frame, 让 trail 末点等于 current bubble. snapshots 末帧通常落后 1 天.
    if (range.endOffset === 0 && themes.length > 0) {
      return [...base, { date: 'current', themes }];
    }
    return base;
  }, [snapshots, range, themes]);

  const focusedTheme = focusedId ? themes.find(t => t.id === focusedId) ?? null : null;

  return (
    <div ref={containerRef}>
      <TrailRangeSlider
        range={range}
        onChange={setRange}
        maxDays={snapshots.length}
      />
      <RotationScatterWithTrails
        themes={themes}
        trailFrames={trailFrames}
        focusedId={focusedId}
        onFocus={toggle}
        mode={mode}
      />
      <FocusedThemePanel theme={focusedTheme} onClose={() => setFocused(null)} />
    </div>
  );
};
