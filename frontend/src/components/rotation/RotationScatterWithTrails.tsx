import { useMemo } from 'react';
import { Scatter, Cell, LabelList } from 'recharts';
import { useNavigate } from 'react-router-dom';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { buildTrails } from '@/lib/trailGradient';
import { useIsMobile } from '@/hooks/useIsMobile';
import { RotationChartFrame, computeBubbleSize } from './RotationChartFrame';
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

export const RotationScatterWithTrails = ({
  themes,
  trailFrames,
  topThemeIds,
  animationDuration,
  showTrails,
  height,
}: Props) => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;

  const points = useMemo(
    () => themesToRotationPoints(themes).map(p => ({
      ...p,
      _bubbleSize: computeBubbleSize(p.size),
    })),
    [themes],
  );
  const themeById = useMemo(() => new Map(themes.map(t => [t.id, t])), [themes]);

  const trails = useMemo(
    () => (showTrails && trailFrames.length > 0
      ? buildTrails(trailFrames, topThemeIds)
      : new Map<string, ReturnType<typeof buildTrails> extends Map<string, infer V> ? V : never>()),
    [showTrails, trailFrames, topThemeIds],
  );

  const tooltipContent = (props: any) => {
    const themeId = props.payload?.[0]?.payload?.themeId as string | undefined;
    const theme = themeId ? themeById.get(themeId) : undefined;
    if (!theme) return null;
    return <ThemeBubbleTooltip {...props} theme={theme} />;
  };

  return (
    <RotationChartFrame height={effectiveHeight} tooltipContent={tooltipContent}>
      <Scatter
        name="current"
        data={points}
        animationDuration={animationDuration}
        onClick={(p: any) => p?.themeId && navigate(`/?theme=${p.themeId}`)}
      >
        {points.map(p => (
          <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />
        ))}
        <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
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
    </RotationChartFrame>
  );
};
