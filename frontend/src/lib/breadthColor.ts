/**
 * MA20 站上率 (0-100) -> 冷暖色.
 * 冷(低站上率/弱市) -> 暖(高站上率/强市), 浅色系, 复用大盘云图刻度.
 * null (无数据) -> 中性灰.
 */
const STOPS: Array<{ at: number; color: string }> = [
  { at: 0, color: '#e0e7ff' },   // 淡紫 — 极冷
  { at: 25, color: '#bae6fd' },  // 浅蓝
  { at: 50, color: '#bbf7d0' },  // 浅绿
  { at: 75, color: '#fef08a' },  // 浅黄
  { at: 100, color: '#fdba74' }, // 浅橙 — 极暖
];

const NO_DATA = '#f1f5f9'; // slate-100

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

/** 站上率 -> 背景色 hex. null/NaN -> 无数据灰. */
export function breadthColor(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return NO_DATA;
  const v = Math.max(0, Math.min(100, rate));
  for (let i = 0; i < STOPS.length - 1; i++) {
    const lo = STOPS[i];
    const hi = STOPS[i + 1];
    if (v >= lo.at && v <= hi.at) {
      const t = hi.at === lo.at ? 0 : (v - lo.at) / (hi.at - lo.at);
      const [r1, g1, b1] = hexToRgb(lo.color);
      const [r2, g2, b2] = hexToRgb(hi.color);
      return `rgb(${lerp(r1, r2, t)}, ${lerp(g1, g2, t)}, ${lerp(b1, b2, t)})`;
    }
  }
  return STOPS[STOPS.length - 1].color;
}

/** 冷暖标签, 用于温度计文案. */
export function breadthLabel(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return '无数据';
  if (rate >= 70) return '过热';
  if (rate >= 50) return '偏暖';
  if (rate >= 30) return '偏冷';
  return '冰点';
}

/**
 * 离散温度级别色 (与 breadthLabel 4 档阈值一致, 取各档中点色).
 * 用于只需区分级别的场景(如温度背景色带), 而非连续渐变.
 * 冰点<30 / 偏冷30-50 / 偏暖50-70 / 过热>=70.
 */
export function breadthLevelColor(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return NO_DATA;
  if (rate >= 70) return '#fdba74';  // 过热 — 浅橙
  if (rate >= 50) return '#fef08a';  // 偏暖 — 浅黄
  if (rate >= 30) return '#bbf7d0';  // 偏冷 — 浅绿
  return '#bae6fd';                  // 冰点 — 浅蓝
}
