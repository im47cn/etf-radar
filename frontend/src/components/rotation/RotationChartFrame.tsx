import {
  ResponsiveContainer, ScatterChart, XAxis, YAxis,
  CartesianGrid, ReferenceLine, ReferenceArea,
} from 'recharts';
import { QUADRANT_COLORS } from '@/lib/rotation';

interface Props {
  height: number;
  /** Scatter 元素必须作为直接 children, Recharts 通过 children walk 提取 */
  children: React.ReactNode;
}

export const computeBubbleSize = (composite: number): number => 8 + (composite / 99) * 12;

/**
 * 散点图静态 frame: 坐标轴 / 网格 / 象限分割线 / 象限色块.
 * Tooltip 已下线 (新版 with-trails 视图用 FocusedThemePanel 承载详情).
 */
export const RotationChartFrame = ({ height, children }: Props) => (
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
      {children}
    </ScatterChart>
  </ResponsiveContainer>
);
