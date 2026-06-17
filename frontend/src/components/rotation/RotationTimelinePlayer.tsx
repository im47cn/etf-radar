import { useMemo, useState } from 'react';
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
  const trailFrames: SnapshotFrame[] = showTrails
    ? collectTrailFrames(tl, dates, TRAIL_WINDOW)
    : [];

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

function collectTrailFrames(
  tl: ReturnType<typeof useSnapshotsTimeline>,
  dates: string[],
  window: number,
): SnapshotFrame[] {
  if (!tl.currentDate || !tl.frame) return [];
  const idx = dates.indexOf(tl.currentDate);
  if (idx === -1) return [];
  const startIdx = Math.max(0, idx - window + 1);
  void dates.slice(startIdx, idx + 1); // v1: only current frame returned
  return [tl.frame];
}
