import { useEffect, useMemo, useState } from 'react';
import { useSnapshotsTimeline } from '@/hooks/useSnapshotsTimeline';
import { useTimelinePlayer } from '@/hooks/useTimelinePlayer';
import { pickTopByComposite } from '@/lib/trailGradient';
import { RotationScatter } from './RotationScatter';
import { RotationScatterWithTrails } from './RotationScatterWithTrails';
import { TimelineControls } from './TimelineControls';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  fallbackThemes: Theme[];
}

const TRAIL_WINDOW = 10;
const TOP_N = 5;

const Banner = ({ children }: { children: React.ReactNode }) => (
  <div className="px-4 py-2 bg-yellow-100 text-yellow-900 text-sm border-b border-yellow-300">
    {children}
  </div>
);

export const RotationTimelinePlayer = ({ fallbackThemes }: Props) => {
  const tl = useSnapshotsTimeline();
  const [showTrails, setShowTrails] = useState(false);

  const dates = tl.index?.snapshots.map(s => s.date) ?? [];

  const player = useTimelinePlayer({
    dates,
    currentDate: tl.currentDate ?? '',
    onAdvance: tl.setDate,
    onPrefetchNeeded: tl.prefetch,
  });

  // Compute derived values unconditionally (hooks rules — no early returns before useMemo)
  const frame: SnapshotFrame = tl.frame ?? { date: tl.currentDate ?? '', themes: fallbackThemes };
  const topThemeIds = useMemo(
    () => pickTopByComposite(frame.themes, TOP_N),
    [frame.themes],
  );
  const trailWindow = useMemo<TrailWindowResult>(
    () => (showTrails ? computeTrailWindow(tl, dates, TRAIL_WINDOW) : { frames: [], missing: [] }),
    // tl 对象引用可能稳定也可能不稳定, 用核心字段做依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showTrails, tl.currentDate, tl.frame, dates.join('|')],
  );
  const trailFrames = trailWindow.frames;
  const missingKey = trailWindow.missing.join('|');

  // cache miss 时触发后台 prefetch, 让下次渲染命中完整尾迹窗口
  useEffect(() => {
    if (trailWindow.missing.length > 0) tl.prefetch(trailWindow.missing);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missingKey]);

  // Branch only on render output
  if (tl.status === 'index-error') {
    return (
      <>
        <Banner>时间轴数据不可用, 正在重试…</Banner>
        <RotationScatter themes={fallbackThemes} />
      </>
    );
  }

  if (tl.status === 'loading' || !tl.currentDate) {
    return (
      <div
        className="animate-pulse h-96 bg-muted rounded"
        data-testid="timeline-loading"
      />
    );
  }

  return (
    <>
      {tl.status === 'frame-error' && (
        <Banner>帧 {tl.error} 不可用, 显示上一帧</Banner>
      )}
      <RotationScatterWithTrails
        themes={frame.themes}
        trailFrames={trailFrames}
        topThemeIds={topThemeIds}
        animationDuration={player.animationDuration}
        showTrails={showTrails}
      />
      <TimelineControls
        dates={dates}
        currentDate={tl.currentDate}
        onDateChange={tl.setDate}
        playing={player.playing}
        speed={player.speed}
        onPlay={player.play}
        onPause={player.pause}
        onStop={player.stop}
        onSpeedChange={player.setSpeed}
        showTrails={showTrails}
        onToggleTrails={setShowTrails}
        disabled={tl.status !== 'ready' && tl.status !== 'frame-error'}
      />
    </>
  );
};

interface TrailWindowResult {
  frames: SnapshotFrame[];
  missing: string[];
}

function computeTrailWindow(
  tl: ReturnType<typeof useSnapshotsTimeline>,
  dates: string[],
  window: number,
): TrailWindowResult {
  if (!tl.currentDate || !tl.frame) return { frames: [], missing: [] };
  const idx = dates.indexOf(tl.currentDate);
  if (idx === -1) return { frames: [tl.frame], missing: [] };
  const startIdx = Math.max(0, idx - window + 1);
  const targetDates = dates.slice(startIdx, idx + 1);
  // 聚合已 cache 命中的历史帧 (老→新), 未命中记入 missing 让上层触发后台 prefetch
  const frames: SnapshotFrame[] = [];
  const missing: string[] = [];
  for (const d of targetDates) {
    const f = tl.getCachedFrame(d);
    if (f) frames.push(f);
    else missing.push(d);
  }
  if (frames.length === 0) frames.push(tl.frame);
  return { frames, missing };
}
