import { useEffect, useState } from 'react';
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis,
  CartesianGrid, ReferenceLine, ReferenceArea, Tooltip, Cell, LabelList,
} from 'recharts';
import { useNavigate } from 'react-router-dom';
import { themesToRotationPoints, QUADRANT_COLORS } from '@/lib/rotation';
import { ThemeBubbleTooltip } from './ThemeBubbleTooltip';
import type { Theme } from '@/types/themes';

interface Props {
  themes: Theme[];
  height?: number;
}

const computeBubbleSize = (composite: number): number => 8 + (composite / 99) * 12;

const useIsMobile = (): boolean => {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
    return window.matchMedia('(max-width: 768px)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia('(max-width: 768px)');
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, []);
  return isMobile;
};

export const RotationScatter = ({ themes, height }: Props) => {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const effectiveHeight = height ?? (isMobile ? 360 : 500);
  const labelFontSize = isMobile ? 9 : 11;

  const points = themesToRotationPoints(themes).map(p => ({
    ...p,
    _bubbleSize: computeBubbleSize(p.size),
  }));
  const themeById = new Map(themes.map(t => [t.id, t]));

  return (
    <ResponsiveContainer width="100%" height={effectiveHeight}>
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
          data={points}
          onClick={(p: any) => p?.themeId && navigate(`/?theme=${p.themeId}`)}
        >
          {points.map(p => (
            <Cell key={p.themeId} fill={QUADRANT_COLORS[p.quadrant]} />
          ))}
          <LabelList dataKey="themeName" position="top" style={{ fontSize: labelFontSize }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
};
