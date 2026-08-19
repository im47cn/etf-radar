import type { SeriesPoint } from '@/types/metals';

interface Props {
  points: SeriesPoint[];
  width?: number;
  height?: number;
  className?: string;
}

/** 迷你趋势线 (纯 SVG, 不引 recharts). points 空时渲染占位. */
export const Sparkline = ({ points, width = 260, height = 48, className }: Props) => {
  if (points.length < 2) return <div style={{ height }} className={className} aria-hidden />;
  const values = points.map(([, v]) => v);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map(([, v], i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - ((v - min) / span) * (height - 4) - 2).toFixed(1)}`)
    .join('');
  const last = values[values.length - 1];
  const first = values[0];
  const stroke = last >= first ? 'stroke-blue-600' : 'stroke-red-600';
  return (
    <svg width={width} height={height} className={className} role="img" aria-label="趋势图">
      <path d={path} fill="none" strokeWidth={1.5} className={stroke} />
    </svg>
  );
};
