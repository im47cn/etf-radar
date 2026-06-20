import { useMemo, useRef } from 'react';
import { useTrailRange } from '@/hooks/useTrailRange';
import { useFocusedTheme } from '@/hooks/useFocusedTheme';
import { useUIState } from '@/providers/uiStateContext';
import { marketViewToRotationMode, themeMatchesView } from '@/lib/marketView';
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

  // 按当前 marketView 收窄散点(cn-all/cn-only/us 分别只显示对应主题集合),
  // 防止 cn-all↔cn-only 切换时散点图不变. trailFrames 内沿用原 themes 即可,
  // 因为 buildTrails 已经按 us/cn 字段过滤掉不可显示的帧.
  const viewThemes = useMemo(
    () => themes.filter(t => themeMatchesView(t, state.marketView)),
    [themes, state.marketView],
  );

  const validThemeIds = useMemo(() => new Set(viewThemes.map(t => t.id)), [viewThemes]);
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

  const focusedTheme = focusedId ? viewThemes.find(t => t.id === focusedId) ?? null : null;

  return (
    <div ref={containerRef}>
      <TrailRangeSlider
        range={range}
        onChange={setRange}
        maxDays={snapshots.length}
      />
      <RotationScatterWithTrails
        themes={viewThemes}
        trailFrames={trailFrames}
        focusedId={focusedId}
        onFocus={toggle}
        mode={mode}
      />
      <FocusedThemePanel theme={focusedTheme} onClose={() => setFocused(null)} />
    </div>
  );
};
