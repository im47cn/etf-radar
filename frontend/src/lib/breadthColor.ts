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

/**
 * 温度 4 档: 单一来源.
 * 图例/tier/纹理/文案全部由此派生, 消除双真源漂移.
 * key 内部键 / label 中文文案 / [min,max) 区间 / mid 取色中点 / hatch 纹理角度.
 * 阈值 25/50/70 与 breadthLabel 完全对齐 (冰点尾部按 MA20 站上率历史 P20 校准).
 */
export const TIERS = [
  { key: 'cold', label: '冰点', min: 0, max: 25, mid: 12, hatch: 45 }, //  '/'
  { key: 'cool', label: '偏冷', min: 25, max: 50, mid: 38, hatch: 0 }, //  '—'
  { key: 'warm', label: '偏暖', min: 50, max: 70, mid: 60, hatch: 90 }, // '|'
  { key: 'hot', label: '过热', min: 70, max: 100, mid: 85, hatch: 135 }, // '\'
] as const;

export type BreadthTier = (typeof TIERS)[number];

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

/** 站上率 -> 所属 tier; 无数据 -> null. 阈值 25/50/70. */
export function breadthTier(rate: number | null | undefined): BreadthTier | null {
  if (rate == null || Number.isNaN(rate)) return null;
  if (rate >= 70) return TIERS[3];
  if (rate >= 50) return TIERS[2];
  if (rate >= 25) return TIERS[1];
  return TIERS[0];
}

/** 冷暖标签, 用于温度计文案. 由 tier 派生, 去重阈值. */
export function breadthLabel(rate: number | null | undefined): string {
  return breadthTier(rate)?.label ?? '无数据';
}

/**
 * 离散温度级别色 (与 breadthLabel 4 档一致, 取各档中点连续采样).
 * 由 breadthColor(tier.mid) 派生, 与连续色阶共用 STOPS 永不漂移.
 * 用于只需区分级别的场景(如温度背景色带), 而非连续渐变.
 */
export function breadthLevelColor(rate: number | null | undefined): string {
  const tier = breadthTier(rate);
  return tier ? breadthColor(tier.mid) : NO_DATA;
}

/**
 * 站上率 -> HTML 面极轻半透明斜线纹理 CSS.
 * 纹理编码 tier(离散 4 档), 4 方向去色后仍可区分档位(a11y).
 * 无数据 -> 无纹理(空对象).
 */
export function breadthTextureCss(
  rate: number | null | undefined,
): { backgroundImage: string; backgroundSize: string } | Record<string, never> {
  const tier = breadthTier(rate);
  if (!tier) return {};
  return {
    backgroundImage: `repeating-linear-gradient(${tier.hatch}deg, transparent 0 4px, rgba(0,0,0,.07) 4px 5px)`,
    backgroundSize: '7px 7px',
  };
}

/**
 * 站上率 -> SVG <pattern> id (供温度计趋势带引用 <defs>).
 * 无数据 -> null. id 与 TIERS.key 一一对应.
 */
export function breadthTierPatternId(rate: number | null | undefined): string | null {
  const tier = breadthTier(rate);
  return tier ? `breadth-tex-${tier.key}` : null;
}
