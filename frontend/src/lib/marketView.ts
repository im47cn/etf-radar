import type { Theme, Strength } from '@/types/themes';
import type { RotationMode } from '@/lib/rotation';

export type MarketView = 'us' | 'cn-all';

export const isCnOnly = (t: Theme): boolean => t.primary_us === null;

export const pickStrength = (t: Theme, mv: MarketView): Strength | null =>
  mv === 'us' ? t.us_strength : t.cn_strength;

export const themeMatchesView = (t: Theme, mv: MarketView): boolean => {
  if (mv === 'us') return !isCnOnly(t) && t.us_strength != null;
  return t.cn_strength != null; // cn-all (含 mapped + A 股专属主题)
};

export const marketViewToRotationMode = (mv: MarketView): RotationMode =>
  mv === 'us' ? 'us' : 'cn';
