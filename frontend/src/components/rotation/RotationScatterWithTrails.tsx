import { memo, useMemo } from 'react';
import { Scatter, Cell, LabelList, Customized, useXAxisScale, useYAxisScale } from 'recharts';
import { themesToRotationPoints, QUADRANT_COLORS, computeBubbleSize } from '@/lib/rotation';
import type { RotationMode } from '@/lib/rotation';
import { buildTrails, type TrailPoint } from '@/lib/trailGradient';
import {
  computeMidTertiles,
  midToStrokeWidth,
  midToStrokeDasharray,
  MID_STROKE_COLOR,
} from '@/lib/midStroke';
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
  /** 持仓命中的主题 id 集合; 命中气泡叠加金色外圈, 不影响布局/交互 */
  ownedThemeIds?: Set<string>;
}

interface OwnedRingPoint {
  themeId: string;
  x: number;
  y: number;
  bubbleSize: number;
}

// 在散点图坐标系上为 ownedThemeIds 命中的气泡叠加一层金色外圈.
// 与 TrailLines 一样必须在 ScatterChart 的 <Customized> 上下文中才能拿到 scale.
const OwnedRings = ({ points }: { points: OwnedRingPoint[] }) => {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (!xScale || !yScale) return null;
  return (
    <g pointerEvents="none">
      {points.map(p => {
        const cx = xScale(p.x);
        const cy = yScale(p.y);
        if (cx == null || cy == null) return null;
        return (
          <circle
            key={`owned-${p.themeId}`}
            cx={cx}
            cy={cy}
            r={p.bubbleSize + 4}
            fill="none"
            stroke="#facc15"
            strokeWidth={2}
          />
        );
      })}
    </g>
  );
};

interface ScatterClickArg {
  themeId?: string;
}

// 三段暖冷色阶: 冷蓝 (旧) → 暖橙 (中段) → 鲜红 (新).
// 比原 #1e40af→#b91c1c 两段更醒目, 中段不再灰蒙, 色温递增暗示方向.
const COLOR_COLD = { r: 0x3b, g: 0x82, b: 0xf6 }; // #3b82f6
const COLOR_WARM = { r: 0xf5, g: 0x9e, b: 0x0b }; // #f59e0b
const COLOR_HOT = { r: 0xdc, g: 0x26, b: 0x26 }; // #dc2626

const lerp = (a: number, b: number, t: number): number =>
  Math.round(a + (b - a) * t);

const interpolateColor = (t: number): string => {
  const [c1, c2, segT] =
    t <= 0.5
      ? [COLOR_COLD, COLOR_WARM, t * 2]
      : [COLOR_WARM, COLOR_HOT, (t - 0.5) * 2];
  return `rgb(${lerp(c1.r, c2.r, segT)},${lerp(c1.g, c2.g, segT)},${lerp(c1.b, c2.b, segT)})`;
};

// 线宽 1→3px 渐变, 头段最粗强化"最新方向"
const TRAIL_WIDTH_MIN = 1;
const TRAIL_WIDTH_MAX = 3;
// 节点 3→7px 渐变, 终点节点放大与当前 bubble 自然衔接
const TRAIL_NODE_MIN = 3;
const TRAIL_NODE_MAX = 7;

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
          // focused: 线宽随 t 1→3px 递增, 头段最粗, 与颜色温度共同强化方向
          const sw = isFocused
            ? TRAIL_WIDTH_MIN + (TRAIL_WIDTH_MAX - TRAIL_WIDTH_MIN) * t
            : 1;
          return (
            <line
              key={`${themeId}-${i}`}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke={color}
              strokeWidth={sw}
              strokeOpacity={isFocused ? 0.85 : 0.18}
              strokeLinecap="round"
            />
          );
        });
      })}
    </g>
  );
};

const Impl = ({ themes, trailFrames, focusedId, onFocus, height, mode, ownedThemeIds }: Props) => {
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;
  const effectiveMode: RotationMode = mode ?? 'us';

  // 移动端把最小半径放大到 14px (~28px 直径), 满足 WCAG/iOS HIG ≥24px 触摸目标
  const points = useMemo(
    () =>
      themesToRotationPoints(themes, effectiveMode).map(p => ({
        ...p,
        _bubbleSize: Math.max(computeBubbleSize(p.size), isMobile ? 14 : 8),
      })),
    [themes, effectiveMode, isMobile],
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

  const ownedRingPoints = useMemo<OwnedRingPoint[]>(() => {
    if (!ownedThemeIds || ownedThemeIds.size === 0) return [];
    return points
      .filter(p => ownedThemeIds.has(p.themeId))
      .map(p => ({ themeId: p.themeId, x: p.x, y: p.y, bubbleSize: p._bubbleSize }));
  }, [points, ownedThemeIds]);

  const focusedTrail = useMemo(() => {
    if (focusedId === null) return null;
    const pts = trails.get(focusedId);
    if (!pts || pts.length === 0) return null;
    return { themeId: focusedId, pts };
  }, [trails, focusedId]);

  return (
    <RotationChartFrame height={effectiveHeight}>
      <Customized component={() => <TrailLines series={trailLineSeries} />} />
      <Customized component={() => <OwnedRings points={ownedRingPoints} />} />
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
          // 聚焦态保留黑色实线描边(优先级最高); 非聚焦态以 MID_STROKE_COLOR 表达 mid 三档强度,
          // 弱档用虚线强化与中档实线的视觉区分.
          const stroke = isFocused ? '#000' : MID_STROKE_COLOR;
          const strokeWidth = isFocused ? 2 : midToStrokeWidth(p.mid, midTertiles);
          const strokeDasharray = isFocused
            ? undefined
            : midToStrokeDasharray(p.mid, midTertiles);
          return (
            <Cell
              key={p.themeId}
              fill={QUADRANT_COLORS[p.quadrant]}
              fillOpacity={isOtherFocused ? 0.2 : 1}
              stroke={stroke}
              strokeWidth={strokeWidth}
              strokeDasharray={strokeDasharray}
              r={p._bubbleSize}
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
              // 节点 r 随 t 3→7px 递增, 终点最大与当前 bubble 自然衔接,
              // 与颜色温度+线宽共同构成方向"三重编码"
              const nodeR =
                TRAIL_NODE_MIN + (TRAIL_NODE_MAX - TRAIL_NODE_MIN) * t;
              return (
                <Cell
                  key={`${themeId}-${i}`}
                  fill={interpolateColor(t)}
                  fillOpacity={0.9}
                  r={nodeR}
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
    prev.mode === next.mode &&
    prev.ownedThemeIds === next.ownedThemeIds,
);
