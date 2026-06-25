/**
 * Phase 2 指标阈值集中常量。
 * 修改阈值仅在此文件，避免散落在 Badge / structureInsight / leaderRule 多处。
 */

export interface StrengthTier {
  min: number;
  label: string;
  color: string;   // tailwind class
}

export const STRENGTH_TIERS: StrengthTier[] = [
  { min: 90, label: '极强', color: 'bg-red-100 text-red-700' },
  { min: 80, label: '强',   color: 'bg-orange-100 text-orange-700' },
  { min: 60, label: '中性', color: 'bg-gray-100 text-gray-600' },
  { min: 40, label: '偏弱', color: 'bg-blue-100 text-blue-700' },
  { min: 0,  label: '弱',   color: 'bg-blue-200 text-blue-800' },
];

export function strengthTier(value: number): StrengthTier {
  return STRENGTH_TIERS.find(t => value >= t.min) ?? STRENGTH_TIERS[STRENGTH_TIERS.length - 1];
}

export const RSI_ZONES = {
  overbought: 70,
  bullishTop: 65,
  bullishBottom: 50,
  oversold: 30,
} as const;

export function rsiColor(value: number): string {
  if (value >= RSI_ZONES.overbought) return 'bg-red-100 text-red-700';
  if (value >= RSI_ZONES.bullishBottom) return 'bg-orange-100 text-orange-700';
  if (value <= RSI_ZONES.oversold) return 'bg-blue-100 text-blue-700';
  return 'bg-gray-100 text-gray-600';
}

export const VOL_RATIO_THRESHOLDS = {
  high: 2.0,
  low: 0.5,
} as const;

export function volRatioColor(value: number): string {
  if (value >= VOL_RATIO_THRESHOLDS.high) return 'bg-red-100 text-red-700';
  if (value <= VOL_RATIO_THRESHOLDS.low) return 'bg-blue-100 text-blue-700';
  return 'bg-gray-100 text-gray-600';
}
