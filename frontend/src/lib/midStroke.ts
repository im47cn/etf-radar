// 气泡边框宽度映射: 当帧 mid 周期强度的三分位 → 离散 3 档线宽。
// 动态分位(而非固定阈值)保证行情整体偏弱/偏强时仍有视觉对比。

export interface MidTertiles {
  q33: number;
  q67: number;
}

export const STROKE_WIDTH_LOW = 1;
export const STROKE_WIDTH_MID = 2;
export const STROKE_WIDTH_HIGH = 3;

/**
 * 计算 mid 数组的 33% / 67% 分位(索引法,与 numpy.percentile interpolation='lower' 近似)。
 * 空数组返回 {0, 0};单值数组 q33=q67=该值。
 */
export function computeMidTertiles(mids: number[]): MidTertiles {
  if (mids.length === 0) return { q33: 0, q67: 0 };
  const sorted = [...mids].sort((a, b) => a - b);
  const idx33 = Math.floor(sorted.length / 3);
  const idx67 = Math.floor((sorted.length * 2) / 3);
  return { q33: sorted[idx33], q67: sorted[idx67] };
}

/**
 * mid 值 → 三档线宽。
 * 边界规则: mid < q33 → LOW, q33 ≤ mid < q67 → MID, mid ≥ q67 → HIGH。
 * 全平分位 (q33==q67) 时,等于该值的样本走 HIGH(保持"中位走中档以上"语义)。
 */
export function midToStrokeWidth(mid: number, t: MidTertiles): number {
  if (mid < t.q33) return STROKE_WIDTH_LOW;
  if (mid < t.q67) return STROKE_WIDTH_MID;
  return STROKE_WIDTH_HIGH;
}

export const MID_STROKE_COLOR = '#374151';
