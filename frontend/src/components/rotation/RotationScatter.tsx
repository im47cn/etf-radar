import { useMemo } from 'react';
import { Scatter, Cell, LabelList } from 'recharts';
import { useNavigate } from 'react-router-dom';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { useIsMobile } from '@/hooks/useIsMobile';
import { RotationChartFrame, computeBubbleSize } from './RotationChartFrame';
import { ThemeBubbleTooltip } from './ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

interface Props {
  themes: Theme[];
  height?: number;
}

export const RotationScatter = ({ themes, height }: Props) => {
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

  const tooltipContent = (props: any) => {
    const themeId = props.payload?.[0]?.payload?.themeId as string | undefined;
    const theme = themeId ? themeById.get(themeId) : undefined;
    if (!theme) return null;
    return <ThemeBubbleTooltip {...props} theme={theme} />;
  };

  return (
    <RotationChartFrame height={effectiveHeight} tooltipContent={tooltipContent}>
      <Scatter
        data={points}
        onClick={(p: any) => p?.themeId && navigate(`/?theme=${p.themeId}`)}
      >
        {points.map(p => (
          <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />
        ))}
        <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
      </Scatter>
    </RotationChartFrame>
  );
};
