import {
  ResponsiveContainer, ScatterChart, XAxis, YAxis,
  CartesianGrid, ReferenceLine, ReferenceArea,
} from 'recharts';
import { QUADRANT_COLORS } from '@/lib/rotation';
import { useIsMobile } from '@/hooks/useIsMobile';

interface Props {
  height: number;
  /** Scatter 元素必须作为直接 children, Recharts 通过 children walk 提取 */
  children: React.ReactNode;
}

/**
 * 散点图静态 frame: 坐标轴 / 网格 / 象限分割线 / 象限色块.
 * Tooltip 已下线 (新版 with-trails 视图用 FocusedThemePanel 承载详情).
 *
 * 移动端: 去掉 XAxis/YAxis 内嵌 label 与多余 margin, 释放图主体可视区域;
 * 坐标轴含义由 RotationPage 顶部副标题 (X/Y 描述) 承载, 避免重复占位.
 */
export const RotationChartFrame = ({ height, children }: Props) => {
  const isMobile = useIsMobile();
  const margin = isMobile
    ? { top: 16, right: 8, bottom: 8, left: 0 }
    : { top: 24, right: 24, bottom: 48, left: 24 };
  const tickStyle = isMobile ? { fontSize: 10 } : undefined;

  return (
    // touch-manipulation 关闭 iOS Safari 双击缩放, 消除 300ms 点击延迟
    <ResponsiveContainer width="100%" height={height} className="touch-manipulation">
      <ScatterChart margin={margin}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          type="number" dataKey="x" domain={[0, 100]}
          tick={tickStyle}
          height={isMobile ? 20 : undefined}
          label={
            isMobile
              ? undefined
              : { value: '长期强度 (60d)', position: 'insideBottom', offset: -10 }
          }
        />
        <YAxis
          type="number" dataKey="y" domain={[0, 100]}
          tick={tickStyle}
          width={isMobile ? 28 : undefined}
          label={
            isMobile
              ? undefined
              : { value: '短期强度 (1d)', angle: -90, position: 'insideLeft' }
          }
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
};
