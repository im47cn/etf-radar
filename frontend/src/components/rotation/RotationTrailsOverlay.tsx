import { useEffect, useMemo, useRef } from 'react';
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
  /** 已缓存的快照帧 (用于绘制 trail 折线), 由调用方传入. */
  snapshots: SnapshotFrame[];
  /**
   * index 中所有可用的快照日期 (升序), 用于决定 slider 上限.
   * 与 snapshots 解耦: snapshots 受 LRU 缓存限制 (默认 10 帧),
   * availableDates 反映服务端实际可拉取的日期总数 (通常 100+).
   * 缺省时回退到 snapshots 的日期数组 (向后兼容).
   */
  availableDates?: string[];
  /**
   * 按需 prefetch 回调. 用户拖动 slider 扩大轨迹范围时,
   * overlay 计算出未缓存的日期集合并调用此函数; 时间线 hook 负责真正拉取.
   */
  onPrefetch?: (dates: string[]) => void;
  /** 持仓命中的主题 id 集合; 透传给散点图叠加金圈 */
  ownedThemeIds?: Set<string>;
}

export const RotationTrailsOverlay = ({
  themes,
  snapshots,
  availableDates,
  onPrefetch,
  ownedThemeIds,
}: Props) => {
  const { range, setRange } = useTrailRange();
  const { state } = useUIState();
  const mode = marketViewToRotationMode(state.marketView);

  // 按当前 marketView 收窄散点(us/cn-all 分别只显示对应主题集合),
  // 防止 us↔cn-all 切换时散点图不变. trailFrames 内沿用原 themes 即可,
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

  // sliderMaxDays: slider 上限来自 availableDates (服务端日期总数),
  // 与 snapshots (已缓存帧数) 解耦. 缺省时回退到 snapshots.length 保持向后兼容.
  const sliderMaxDays = availableDates?.length ?? snapshots.length;

  // 按需 prefetch: 当 range.startOffset 改变时, 计算 trail 需要的日期窗口,
  // 找出尚未缓存的日期并触发拉取. 用 ref 缓存上次请求过的日期, 防止抖动.
  const cachedDates = useMemo(() => new Set(snapshots.map(s => s.date)), [snapshots]);
  const lastRequestedRef = useRef<string>('');
  useEffect(() => {
    if (!onPrefetch || !availableDates || availableDates.length === 0) return;
    const lastIdx = availableDates.length - 1;
    const startIdx = Math.max(0, lastIdx + range.startOffset);
    const endIdx = Math.max(startIdx, lastIdx + range.endOffset);
    const needed = availableDates.slice(startIdx, endIdx + 1);
    const missing = needed.filter(d => !cachedDates.has(d));
    if (missing.length === 0) return;
    // 去重: 同一组 missing 不重复触发 (range 抖动期间避免雪崩)
    const key = missing.join(',');
    if (lastRequestedRef.current === key) return;
    lastRequestedRef.current = key;
    onPrefetch(missing);
  }, [range.startOffset, range.endOffset, availableDates, cachedDates, onPrefetch]);

  return (
    <div ref={containerRef}>
      <TrailRangeSlider
        range={range}
        onChange={setRange}
        maxDays={sliderMaxDays}
      />
      <RotationScatterWithTrails
        themes={viewThemes}
        trailFrames={trailFrames}
        focusedId={focusedId}
        onFocus={toggle}
        mode={mode}
        ownedThemeIds={ownedThemeIds}
      />
      <FocusedThemePanel theme={focusedTheme} onClose={() => setFocused(null)} />
    </div>
  );
};
