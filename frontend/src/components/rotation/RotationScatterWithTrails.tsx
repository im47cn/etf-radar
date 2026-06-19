import { memo, useMemo } from 'react';
import { Scatter, Cell, LabelList, Customized, useXAxisScale, useYAxisScale } from 'recharts';
import { themesToRotationPoints, QUADRANT_COLORS, computeBubbleSize } from '@/lib/rotation';
import type { RotationMode } from '@/lib/rotation';
import { buildTrails, type TrailPoint } from '@/lib/trailGradient';
import { useIsMobile } from '@/hooks/useIsMobile';
import { RotationChartFrame } from './RotationChartFrame';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  trailFrames: SnapshotFrame[];
  focusedId: string | null;
  onFocus: (themeId: string) => void;
  height?: number;
  mode?: RotationMode;
}

interface ScatterClickArg {
  themeId?: string;
}

const interpolateColor = (t: number): string => {
  const start = { r: 0x1e, g: 0x40, b: 0xaf };
  const end = { r: 0xb9, g: 0x1c, b: 0x1c };
  const r = Math.round(start.r + (end.r - start.r) * t);
  const g = Math.round(start.g + (end.g - start.g) * t);
  const b = Math.round(start.b + (end.b - start.b) * t);
  return `rgb(${r},${g},${b})`;
};

interface TrailLineSeries {
  themeId: string;
  points: TrailPoint[];
  isFocused: boolean;
}

// Renders line segments connecting trail points; consumes Recharts axis scales
// via hooks (only valid inside ScatterChart context via <Customized>).
// trailFrames 已由 RotationTrailsOverlay 在 endOffset===0 时追加 T-0 frame,
// 所以 trail 末点天然等于 current bubble 位置, 无需额外连接段.
const TrailLines = ({ series }: { series: TrailLineSeries[] }) => {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale) return null;
  return (
    <g pointerEvents="none">
      {series.flatMap(({ themeId, points, isFocused }) => {
        if (points.length < 2) return [];
        const total = points.length;
        return points.slice(1).map((pt, i) => {
          const prev = points[i];
          const x1 = xScale(prev.x);
          const y1 = yScale(prev.y);
          const x2 = xScale(pt.x);
          const y2 = yScale(pt.y);
          if (x1 == null || y1 == null || x2 == null || y2 == null) return null;
          const t = total <= 2 ? 0 : (i + 0.5) / (total - 1);
          const color = isFocused ? interpolateColor(t) : '#94a3b8';
          return (
            <line
              key={`${themeId}-${i}`}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke={color}
              strokeWidth={isFocused ? 2 : 1}
              strokeOpacity={isFocused ? 0.75 : 0.18}
              strokeLinecap="round"
            />
          );
        });
      })}
    </g>
  );
};

const Impl = ({ themes, trailFrames, focusedId, onFocus, height, mode }: Props) => {
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;
  const effectiveMode: RotationMode = mode ?? 'us';

  const points = useMemo(
    () =>
      themesToRotationPoints(themes, effectiveMode).map(p => ({
        ...p,
        _bubbleSize: computeBubbleSize(p.size),
      })),
    [themes, effectiveMode],
  );

  const trails = useMemo(() => buildTrails(trailFrames), [trailFrames]);

  const trailLineSeries = useMemo<TrailLineSeries[]>(() => {
    const out: TrailLineSeries[] = [];
    for (const [themeId, pts] of trails) {
      const isFocused = focusedId === themeId;
      const isOtherFocused = focusedId !== null && !isFocused;
      if (isOtherFocused || pts.length < 2) continue;
      out.push({ themeId, points: pts, isFocused });
    }
    return out;
  }, [trails, focusedId]);

  return (
    <RotationChartFrame height={effectiveHeight}>
      <Customized component={() => <TrailLines series={trailLineSeries} />} />
      <Scatter
        name="current"
        data={points}
        isAnimationActive={false}
        onClick={(p) => {
          const themeId = (p as unknown as ScatterClickArg)?.themeId;
          if (themeId) onFocus(themeId);
        }}
      >
        {points.map(p => {
          const isFocused = focusedId === p.themeId;
          const isOtherFocused = focusedId !== null && !isFocused;
          return (
            <Cell
              key={p.themeId}
              fill={QUADRANT_COLORS[p.quadrant]}
              fillOpacity={isOtherFocused ? 0.2 : 1}
              stroke={isFocused ? '#000' : 'none'}
              strokeWidth={isFocused ? 2 : 0}
            />
          );
        })}
        <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
      </Scatter>

      {Array.from(trails.entries()).map(([themeId, pts]) => {
        const isFocused = focusedId === themeId;
        const isOtherFocused = focusedId !== null && !isFocused;
        if (isOtherFocused || pts.length === 0) return null;
        const total = pts.length;
        // Recharts uses `opacity` field in data as SVG path opacity, overriding
        // Cell's fillOpacity. Override to 0.9 for the focused trail so the
        // blue→red gradient stays visible.
        const data = isFocused ? pts.map(pt => ({ ...pt, opacity: 0.9 })) : pts;
        return (
          <Scatter
            key={`trail-${themeId}`}
            name={`trail-${themeId}`}
            data={data}
            isAnimationActive={false}
          >
            {pts.map((pt, i) => {
              const t = total <= 1 ? 0 : i / (total - 1);
              const color = isFocused ? interpolateColor(t) : '#94a3b8';
              return (
                <Cell
                  key={`${themeId}-${i}`}
                  fill={color}
                  fillOpacity={isFocused ? 0.9 : pt.opacity}
                  r={isFocused ? 5 : 4}
                  pointerEvents="none"
                />
              );
            })}
          </Scatter>
        );
      })}
    </RotationChartFrame>
  );
};

export const RotationScatterWithTrails = memo(
  Impl,
  (prev, next) =>
    prev.themes === next.themes &&
    prev.trailFrames === next.trailFrames &&
    prev.focusedId === next.focusedId &&
    prev.height === next.height &&
    prev.onFocus === next.onFocus &&
    prev.mode === next.mode,
);
