import { memo, useMemo } from 'react';
import { Scatter, Cell, LabelList, Customized, useXAxisScale, useYAxisScale } from 'recharts';
import { themesToRotationPoints, QUADRANT_COLORS, computeBubbleSize } from '@/lib/rotation';
import type { RotationMode } from '@/lib/rotation';
import { buildTrails, type TrailPoint } from '@/lib/trailGradient';
import { computeMidTertiles, midToStrokeWidth, MID_STROKE_COLOR } from '@/lib/midStroke';
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

  // 当帧 mid 三分位; 用于将非聚焦气泡按 mid 周期强度映射到 LOW/MID/HIGH 三档线宽
  const midTertiles = useMemo(
    () => computeMidTertiles(points.map(p => p.mid)),
    [points],
  );

  const trails = useMemo(
    () => buildTrails(trailFrames, effectiveMode),
    [trailFrames, effectiveMode],
  );

  // 性能优化(方案 C):仅在 focused 时渲染 trail,避免 N 主题 × M 帧 = N*M Cell
  // 全量重渲染。默认无聚焦状态完全不渲染 trail,与 FocusedThemePanel 范式一致。
  const trailLineSeries = useMemo<TrailLineSeries[]>(() => {
    if (focusedId === null) return [];
    const pts = trails.get(focusedId);
    if (!pts || pts.length < 2) return [];
    return [{ themeId: focusedId, points: pts, isFocused: true }];
  }, [trails, focusedId]);

  const focusedTrail = useMemo(() => {
    if (focusedId === null) return null;
    const pts = trails.get(focusedId);
    if (!pts || pts.length === 0) return null;
    return { themeId: focusedId, pts };
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
          // 聚焦态保留黑色描边(优先级最高); 非聚焦态以 MID_STROKE_COLOR 表达 mid 三档强度
          const stroke = isFocused ? '#000' : MID_STROKE_COLOR;
          const strokeWidth = isFocused ? 2 : midToStrokeWidth(p.mid, midTertiles);
          return (
            <Cell
              key={p.themeId}
              fill={QUADRANT_COLORS[p.quadrant]}
              fillOpacity={isOtherFocused ? 0.2 : 1}
              stroke={stroke}
              strokeWidth={strokeWidth}
            />
          );
        })}
        <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
      </Scatter>

      {focusedTrail && (() => {
        const { themeId, pts } = focusedTrail;
        const total = pts.length;
        // Recharts 将 data 中的 `opacity` 当作 SVG path opacity,覆盖 Cell 的 fillOpacity。
        // 焦点 trail 统一覆为 0.9,蓝→红渐变才不被淡出。
        const data = pts.map(pt => ({ ...pt, opacity: 0.9 }));
        return (
          <Scatter
            key={`trail-${themeId}`}
            name={`trail-${themeId}`}
            data={data}
            isAnimationActive={false}
          >
            {pts.map((_pt, i) => {
              const t = total <= 1 ? 0 : i / (total - 1);
              return (
                <Cell
                  key={`${themeId}-${i}`}
                  fill={interpolateColor(t)}
                  fillOpacity={0.9}
                  r={5}
                  pointerEvents="none"
                />
              );
            })}
          </Scatter>
        );
      })()}
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
