import { useMemo } from 'react';
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis,
  CartesianGrid, ReferenceLine, ReferenceArea, Tooltip, Cell, LabelList,
} from 'recharts';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { buildTrails } from '@/lib/trailGradient';
import { ThemeBubbleTooltip } from './ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';
import type { SnapshotFrame } from '@/types/snapshots';

interface Props {
  themes: Theme[];
  trailFrames: SnapshotFrame[];
  topThemeIds: Set<string>;
  animationDuration: number;
  showTrails: boolean;
  height?: number;
}

const computeBubbleSize = (composite: number): number => 8 + (composite / 99) * 12;

export const RotationScatterWithTrails = ({
  themes,
  trailFrames,
  topThemeIds,
  animationDuration,
  showTrails,
  height = 500,
}: Props) => {
  const points = themesToRotationPoints(themes).map(p => ({
    ...p,
    _bubbleSize: computeBubbleSize(p.size),
  }));
  const themeById = useMemo(() => new Map(themes.map(t => [t.id, t])), [themes]);

  const trails = useMemo(
    () => (showTrails && trailFrames.length > 0
      ? buildTrails(trailFrames, topThemeIds)
      : new Map<string, ReturnType<typeof buildTrails> extends Map<string, infer V> ? V : never>()),
    [showTrails, trailFrames, topThemeIds],
  );

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 24, right: 24, bottom: 48, left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number" dataKey="x" domain={[0, 100]}
          label={{ value: '长期强度 (60d)', position: 'insideBottom', offset: -10 }}
        />
        <YAxis
          type="number" dataKey="y" domain={[0, 100]}
          label={{ value: '短期强度 (1d)', angle: -90, position: 'insideLeft' }}
        />
        <ReferenceLine x={50} stroke="#94a3b8" strokeDasharray="3 3" />
        <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="3 3" />
        <ReferenceArea x1={50} x2={100} y1={50} y2={100} fill={QUADRANT_COLORS.leading} fillOpacity={0.05} />
        <ReferenceArea x1={0}  x2={50}  y1={50} y2={100} fill={QUADRANT_COLORS.rising}  fillOpacity={0.05} />
        <ReferenceArea x1={0}  x2={50}  y1={0}  y2={50}  fill={QUADRANT_COLORS.lagging} fillOpacity={0.05} />
        <ReferenceArea x1={50} x2={100} y1={0}  y2={50}  fill={QUADRANT_COLORS.fading}  fillOpacity={0.05} />
        <Tooltip
          cursor={{ strokeDasharray: '3 3' }}
          content={(props: any) => {
            const themeId = props.payload?.[0]?.payload?.themeId as string | undefined;
            const theme = themeId ? themeById.get(themeId) : undefined;
            if (!theme) return null;
            return <ThemeBubbleTooltip {...props} theme={theme} />;
          }}
        />

        <Scatter
          name="current"
          data={points}
          animationDuration={animationDuration}
        >
          {points.map(p => (
            <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />
          ))}
          <LabelList dataKey="themeName" position="top" style={{ fontSize: 11 }} />
        </Scatter>

        {Array.from(trails.entries()).map(([themeId, pts]) =>
          pts.length > 0 ? (
            <Scatter
              key={`trail-${themeId}`}
              name={`trail-${themeId}`}
              data={pts}
              isAnimationActive={false}
            >
              {pts.map((pt, i) => (
                <Cell
                  key={`${themeId}-${i}`}
                  fill="#94a3b8"
                  fillOpacity={pt.opacity}
                  r={4}
                />
              ))}
            </Scatter>
          ) : null,
        )}
      </ScatterChart>
    </ResponsiveContainer>
  );
};
